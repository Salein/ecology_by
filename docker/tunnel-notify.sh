#!/bin/sh
# Quick tunnel + опциональный webhook при каждом старте контейнера, когда в логе появился URL.
# Повторные строки с тем же URL в одной сессии игнорируются.
set -eu
ORIGIN="${TUNNEL_ORIGIN_SERVICE:-edge}"
DATA_DIR="/data"
STATE="${DATA_DIR}/last_tunnel_url.txt"
PIPE=/tmp/cloudflared-out.pipe

mkdir -p "$DATA_DIR"
rm -f "$PIPE"
mkfifo "$PIPE"

cloudflared tunnel --no-autoupdate --url "http://${ORIGIN}:80" >"$PIPE" 2>&1 &
CF_PID=$!

cleanup() {
  kill "$CF_PID" 2>/dev/null || true
  rm -f "$PIPE"
  exit 0
}
trap cleanup TERM INT HUP

notify_url() {
  url="$1"
  printf '%s' "$url" >"$STATE"

  if [ -n "${NOTIFY_WEBHOOK_URL:-}" ]; then
    escaped=$(printf '%s' "$url" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g')
    curl -fsS -X POST -H "Content-Type: application/json" \
      -d "{\"text\":\"${escaped}\",\"message\":\"${escaped}\"}" \
      "$NOTIFY_WEBHOOK_URL" >/dev/null 2>&1 || true
  fi
}

NOTIFIED_URL=""
while IFS= read -r line; do
  printf '%s\n' "$line"
  url=$(printf '%s\n' "$line" | sed -n 's/.*\(https:\/\/[A-Za-z0-9-]*\.trycloudflare\.com\).*/\1/p' | head -n1)
  [ -z "$url" ] && continue
  [ "$url" = "$NOTIFIED_URL" ] && continue
  NOTIFIED_URL="$url"
  notify_url "$url"
done <"$PIPE"

wait "$CF_PID"
