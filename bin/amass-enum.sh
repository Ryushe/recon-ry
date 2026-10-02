#!/usr/bin/env bash
# Version-aware passive subdomain enumeration via amass, for recon-ry's
# subdomain_enum stage.
#
# Why this exists:
#   * amass v4 is a one-shot CLI:  amass enum -passive -d <d> ...
#   * amass v5 is a client/engine split. `amass enum` submits work to an engine
#     and `amass subs` reads names back out of the graph DB. With no engine
#     reachable, v5 HANGS INDEFINITELY - it does not even print `-h`.
#   * The previous recon-ry command also passed `-rf <rate>`, but `-rf` is
#     "path to a file providing untrusted DNS resolvers" in every version, and
#     it never redirected stdout to {{OUTPUT}}, so results were discarded.
#
# Usage: amass-enum.sh <roots-file> <output-file> [rate-qps]
set -uo pipefail
ROOTS="${1:?roots file required}"; OUT="${2:?output file required}"; RATE="${3:-5}"
HARD_TIMEOUT="${AMASS_HARD_TIMEOUT:-600}"      # per-root ceiling; never hang forever
ENGINE_WAIT="${AMASS_ENGINE_WAIT:-25}"

command -v amass >/dev/null || { echo "[amass] FATAL: amass not installed" >&2; exit 1; }
RAW_VER="$(amass -version 2>&1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
MAJOR="$(printf '%s' "${RAW_VER#v}" | cut -d. -f1)"
: "${MAJOR:=0}"
echo "[amass] version=${RAW_VER:-unknown} major=$MAJOR rate=${RATE}qps" >&2

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
: > "$tmp/all"
roots=0; ok=0

ensure_engine_v5() {
  pgrep -f '[a]mass engine' >/dev/null 2>&1 && return 0
  echo "[amass] v5 detected; starting local engine" >&2
  nohup amass engine -log-dir "$tmp/enginelog" >"$tmp/engine.out" 2>&1 &
  local w=0
  while [ "$w" -lt "$ENGINE_WAIT" ]; do
    pgrep -f '[a]mass engine' >/dev/null 2>&1 && { echo "[amass] engine up" >&2; return 0; }
    grep -qiE 'failed to start the engine' "$tmp/engine.out" 2>/dev/null && {
      echo "[amass] ENGINE FAILED: $(tr -d '\n' < "$tmp/engine.out" | cut -c1-160)" >&2
      return 1
    }
    sleep 2; w=$((w+2))
  done
  echo "[amass] ENGINE TIMEOUT after ${ENGINE_WAIT}s" >&2
  return 1
}

if [ "$MAJOR" -ge 5 ]; then
  if ! ensure_engine_v5; then
    cat >&2 <<'MSG'
[amass] FATAL: amass v5 requires a reachable engine, and it could not start.
[amass]   v5 resolves its own bootstrap hosts (e.g. bgp.tools) through its own
[amass]   DNS stack aimed at public resolvers. If outbound DNS to public
[amass]   resolvers is firewalled, the engine exits at startup and `amass enum`
[amass]   would otherwise hang forever with no output.
[amass]   v5 exposes no resolver flag/config (checked config.yaml,
[amass]   datasources.yaml, -r/-rf, AMASS_* env), so there is no in-tool fix.
[amass]   Options: allow outbound DNS to a public resolver, point AMASS_ENGINE_HOST
[amass]   at a working remote engine, or pin amass v4 (one-shot, no engine).
MSG
    : > "$OUT"; exit 1
  fi
fi

while IFS= read -r root; do
  root="${root%%[[:space:]]*}"; [ -z "$root" ] && continue
  case "$root" in \#*) continue;; esac
  root="${root#\*.}"
  roots=$((roots+1))

  if [ "$MAJOR" -ge 5 ]; then
    timeout "$HARD_TIMEOUT" amass enum -d "$root" -silent -nocolor >/dev/null 2>"$tmp/$root.err"
    rc=$?
    timeout 120 amass subs -d "$root" -names -silent -nocolor 2>/dev/null >"$tmp/$root.out" || true
  else
    timeout "$HARD_TIMEOUT" amass enum -passive -d "$root" -rqps "$RATE" -silent -nocolor \
      >"$tmp/$root.out" 2>"$tmp/$root.err"
    rc=$?
  fi

  # grep -c prints a count AND exits non-zero on no-match; a `|| echo 0`
  # here would append a SECOND zero and break the integer tests below.
  n=$(grep -coE '^[A-Za-z0-9_.-]+\.[A-Za-z]{2,}$' "$tmp/$root.out" 2>/dev/null | head -1)
  n=${n:-0}
  if [ "$rc" -eq 124 ]; then
    echo "[amass] $root: hit ${HARD_TIMEOUT}s ceiling; keeping $n partial names" >&2
  elif [ "$rc" -ne 0 ]; then
    echo "[amass] $root: exit=$rc ($(tail -1 "$tmp/$root.err" 2>/dev/null | cut -c1-70))" >&2
  else
    echo "[amass] $root: $n names" >&2
  fi
  [ "$n" -gt 0 ] && { cat "$tmp/$root.out" >> "$tmp/all"; ok=$((ok+1)); }
done < "$ROOTS"

grep -hoE '^[A-Za-z0-9_.-]+\.[A-Za-z]{2,}$' "$tmp/all" 2>/dev/null | tr 'A-Z' 'a-z' | sort -u > "$OUT" || : > "$OUT"
echo "[amass] roots=$roots with_results=$ok names=$(wc -l < "$OUT")" >&2
exit 0
