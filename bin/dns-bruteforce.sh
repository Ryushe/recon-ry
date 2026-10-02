#!/usr/bin/env bash
# DNS subdomain bruteforce for recon-ry's subdomain_enum stage.
#
# SCOPE RULE: reads roots from the project's wildcard roots file (wild.txt via
# {{ROOTS_FILE}}) ONLY. Bruteforcing invents new hostnames under a root, which is
# in scope only where the program grants a wildcard (*.root). Exact-host scope
# entries are deliberately never bruteforced.
#
# Usage: dns-bruteforce.sh <roots-file> <output-file> [rate-limit]
set -uo pipefail
ROOTS="${1:?roots file required}"; OUT="${2:?output file required}"; RATE="${3:-25}"

WORDLIST="${RECON_RY_DNS_WORDLIST:-}"
if [ -z "$WORDLIST" ]; then
  # Case-insensitive search: this box ships SecLists as "Seclists" (lowercase l),
  # which is why recon-ry's ffuf resolver silently fell back to a 27-word list.
  for c in \
    /usr/share/wordlists/Seclists/Discovery/DNS/subdomains-top1million-20000.txt \
    /usr/share/wordlists/SecLists/Discovery/DNS/subdomains-top1million-20000.txt \
    /usr/share/wordlists/Seclists/Discovery/DNS/subdomains-top1million-5000.txt \
    /usr/share/seclists/Discovery/DNS/subdomains-top1million-5000.txt ; do
    [ -f "$c" ] && { WORDLIST="$c"; break; }
  done
fi
[ -n "$WORDLIST" ] && [ -f "$WORDLIST" ] || { echo "[dnsbf] FATAL: no DNS wordlist found" >&2; exit 1; }

command -v dnsx >/dev/null || { echo "[dnsbf] FATAL: dnsx not installed" >&2; exit 1; }

# Only resolvers reachable here: Mullvad's 10.64.0.1, else the local stub.
RESOLVER=""
for r in "${RECON_RY_DNS_RESOLVER:-}" 10.64.0.1 127.0.0.53; do
  [ -z "$r" ] && continue
  if timeout 6 dig +short +time=3 +tries=1 "@$r" A example.com >/dev/null 2>&1; then RESOLVER="$r"; break; fi
done
[ -n "$RESOLVER" ] || { echo "[dnsbf] FATAL: no working resolver" >&2; exit 1; }

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
: > "$tmp/all"
echo "[dnsbf] wordlist=$WORDLIST ($(wc -l < "$WORDLIST") words) resolver=$RESOLVER rate=${RATE}/s" >&2

roots=0; ok=0
while IFS= read -r root; do
  root="${root%%[[:space:]]*}"; [ -z "$root" ] && continue
  case "$root" in \#*) continue;; esac
  root="${root#\*.}"                        # tolerate "*.example.com" form
  roots=$((roots+1))

  # Flag wildcard DNS: if a random label resolves, every brute candidate will
  # "resolve" too. dnsx -auto-wildcard filters it; we log it so the operator
  # knows why a root yields little.
  probe="zzz$RANDOM$RANDOM-nxcheck.$root"
  if timeout 8 dig +short +time=3 +tries=1 "@$RESOLVER" A "$probe" 2>/dev/null | grep -qE '^[0-9]+\.'; then
    echo "[dnsbf] $root: WILDCARD DNS detected - relying on dnsx -auto-wildcard" >&2
  fi

  if timeout "${RECON_RY_DNS_TIMEOUT:-3600}" dnsx \
       -d "$root" -w "$WORDLIST" \
       -r "$RESOLVER" -rl "$RATE" \
       -auto-wildcard -silent -a -resp-only=false \
       -o "$tmp/$root.out" >/dev/null 2>"$tmp/$root.err"; then
    n=$(wc -l < "$tmp/$root.out" 2>/dev/null || echo 0)
    echo "[dnsbf] $root: $n names" >&2
    cat "$tmp/$root.out" >> "$tmp/all" 2>/dev/null
    ok=$((ok+1))
  else
    echo "[dnsbf] $root: dnsx FAILED ($(tail -1 "$tmp/$root.err" 2>/dev/null | cut -c1-80))" >&2
  fi
done < "$ROOTS"

grep -oiE '^[a-z0-9_.-]+\.[a-z]{2,}' "$tmp/all" 2>/dev/null | tr 'A-Z' 'a-z' | sort -u > "$OUT" || : > "$OUT"
echo "[dnsbf] roots=$roots ok=$ok names=$(wc -l < "$OUT")" >&2
[ "$roots" -gt 0 ] && [ "$ok" -eq 0 ] && { echo "[dnsbf] FATAL: every root failed" >&2; exit 1; }
exit 0
