#!/usr/bin/env bash
# Robust Wayback CDX collector for recon-ry's archive stage.
# Replaces bare `waybackurls`, which silently emits partial/empty output when
# archive.org rate-limits (HTTP 429) and gives no non-zero exit to detect it.
#
# Usage: cdx-archive-urls.sh <input-domains-file> <output-urls-file>
set -uo pipefail
IN="${1:?input file required}"; OUT="${2:?output file required}"
UA='Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36'
MAX_TRIES="${CDX_MAX_TRIES:-6}"
BASE_SLEEP="${CDX_BASE_SLEEP:-15}"
TIMEOUT="${CDX_TIMEOUT:-300}"

tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
ok=0; failed=0; total_domains=0

while IFS= read -r dom; do
  dom="${dom%%[[:space:]]*}"; [ -z "$dom" ] && continue
  case "$dom" in \#*) continue;; esac
  dom="${dom#\*.}"
  total_domains=$((total_domains+1))
  got=0
  for try in $(seq 1 "$MAX_TRIES"); do
    code=$(curl -sS --max-time "$TIMEOUT" -A "$UA" \
      "http://web.archive.org/cdx/search/cdx?url=*.${dom}/*&output=text&fl=original&collapse=urlkey" \
      -o "$tmp/$dom.raw" -w '%{http_code}' 2>/dev/null)
    if [ "$code" = "200" ] && [ -s "$tmp/$dom.raw" ]; then
      cat "$tmp/$dom.raw" >> "$tmp/all.raw"; got=1
      echo "[cdx] $dom: HTTP 200, $(wc -l < "$tmp/$dom.raw") rows (try $try)" >&2
      break
    fi
    echo "[cdx] $dom: HTTP ${code:-err} on try $try/$MAX_TRIES; backing off $((BASE_SLEEP*try))s" >&2
    sleep $((BASE_SLEEP*try))
  done
  if [ "$got" = "1" ]; then ok=$((ok+1)); else failed=$((failed+1)); echo "[cdx] $dom: EXHAUSTED retries" >&2; fi
done < "$IN"

grep -aoE '^https?://[^[:space:]]+' "$tmp/all.raw" 2>/dev/null | sort -u > "$OUT" || : > "$OUT"
echo "[cdx] domains=$total_domains ok=$ok failed=$failed urls=$(wc -l < "$OUT")" >&2

# Fail loudly when nothing was collected but work was requested, so recon-ry
# logs a real failure instead of a silent "added 0 new entries".
if [ "$total_domains" -gt 0 ] && [ "$ok" -eq 0 ]; then
  echo "[cdx] FATAL: every CDX query failed (likely sustained 429). Not an empty archive." >&2
  exit 1
fi
exit 0
