#!/usr/bin/env python3
"""Offline, fail-closed scope checks. Never resolve DNS or contact a target."""
import argparse
import ipaddress
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


def host_of(value):
    """Accept a plain host/IP or HTTP(S) URL; reject ambiguous authorities."""
    value = value.strip()
    if not value or any(c.isspace() or ord(c) < 32 for c in value) or "\\" in value:
        raise ValueError("invalid host/URL")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    parsed = urlsplit(value if "://" in value else "//" + value)
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        raise ValueError("only HTTP(S) URLs are supported")
    if parsed.username is not None or parsed.password is not None or not parsed.hostname:
        raise ValueError("invalid authority")
    if parsed.port is not None and not 1 <= parsed.port <= 65535:
        raise ValueError("invalid port")
    host = parsed.hostname.lower().rstrip(".")
    try:
        return str(ipaddress.ip_address(host))
    except ValueError:
        pass
    if len(host) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split(".")):
        raise ValueError("invalid DNS hostname (use ASCII/IDNA)")
    return host


def parse_rule(value):
    if "/" in value:
        return "network", ipaddress.ip_network(value, strict=True)
    wildcard = value.startswith("*.")
    bare = value[2:] if wildcard else value
    host = host_of(bare)
    # Scope files contain hosts, not URLs, paths, credentials or port policies.
    if bare.lower().rstrip(".") != host and bare != "[" + host + "]":
        raise ValueError("scope entries must be hostnames, IPs or CIDRs")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        if wildcard:
            raise ValueError("wildcard IP is not valid scope")
    return ("wildcard" if wildcard else "exact"), host


def load_rules(path):
    rules = []
    if path:
        for number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            value = raw.strip()
            if not value or value.startswith("#"):
                continue
            try:
                rules.append(parse_rule(value))
            except ValueError as exc:
                raise ValueError(f"invalid scope entry at line {number}: {exc}") from exc
    return rules


def matches(rule, host):
    kind, value = rule
    if kind == "exact":
        return host == value
    if kind == "wildcard":
        return host != value and host.endswith("." + value)
    try:
        return ipaddress.ip_address(host) in value
    except ValueError:
        return False


class Scope:
    def __init__(self, include, exclude=(), exact_host=""):
        if not include and not exact_host:
            raise ValueError("explicit nonempty scope is required; DNS is not authorization")
        self.include = include
        self.exclude = exclude
        self.exact_host = host_of(exact_host) if exact_host else ""

    def allows(self, value):
        try:
            host = host_of(value)
        except ValueError:
            return False
        if any(matches(rule, host) for rule in self.exclude):
            return False
        if self.exact_host and host != self.exact_host:
            return False
        return not self.include or any(matches(rule, host) for rule in self.include)


def filter_file(scope, source, destination):
    """Atomic replacement permits in-place filtering without transient empties."""
    source, destination = Path(source), Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".scope-", dir=destination.parent)
    rejected = 0
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out, source.open(encoding="utf-8") as inp:
            for raw in inp:
                if scope.allows(raw.strip()):
                    out.write(raw.strip() + "\n")
                elif raw.strip():
                    rejected += 1
        os.replace(name, destination)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return rejected


def crawl_regex(scope, source):
    # Only approved input hosts, not every host under a wildcard root. This
    # deliberately narrows crawling; additional discovered URLs pass the gate.
    hosts = sorted({host_of(line) for line in Path(source).read_text().splitlines() if scope.allows(line)})
    if not hosts:
        raise ValueError("no authorized crawler input")
    authorities = [re.escape("[" + h + "]" if ":" in h else h) + r"\.?" for h in hosts]
    return r"(?i)^https?://(?:" + "|".join(authorities) + r")(?::[0-9]+)?(?:[/?#]|$)"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("validate", "filter", "check", "crawl-regex"))
    p.add_argument("--scope-file", default=os.environ.get("RECON_RY_SCOPE_FILE", ""))
    p.add_argument("--out-scope-file", default=os.environ.get("RECON_RY_OUT_SCOPE_FILE", ""))
    p.add_argument("--exact-host", default=os.environ.get("RECON_RY_EXACT_HOST", ""))
    p.add_argument("--input")
    p.add_argument("--output")
    p.add_argument("--value")
    args = p.parse_args()
    try:
        include = load_rules(args.scope_file)
        if args.scope_file and not include:
            raise ValueError("scope file is empty")
        scope = Scope(include, load_rules(args.out_scope_file), args.exact_host)
        if args.action == "filter":
            if not args.input or not args.output:
                p.error("filter needs --input and --output")
            count = filter_file(scope, args.input, args.output)
            if count:
                print(f"scope: rejected {count} candidate(s)", file=sys.stderr)
        elif args.action == "check":
            return 0 if args.value and scope.allows(args.value) else 1
        elif args.action == "crawl-regex":
            if not args.input:
                p.error("crawl-regex needs --input")
            print(crawl_regex(scope, args.input))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"scope: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
