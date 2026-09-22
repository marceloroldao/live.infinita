#!/usr/bin/env bash
set -euo pipefail

BASE="${LIVE_COGNITIVE_URL:-http://127.0.0.1:8090}"
INTERVAL="${LIVE_COGNITIVE_WATCH_SECONDS:-10}"

echo "Watching Server Cognitive RC1 at $BASE every ${INTERVAL}s"
echo "Ctrl-C to stop."

while true; do
  printf '%s ' "$(date -Is)"
  if ! curl -fsS "$BASE/soak"; then
    echo
    echo "RC1 soak endpoint unavailable" >&2
  else
    echo
  fi
  sleep "$INTERVAL"
done
