#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${LIVE_COGNITIVE_SMOKE_PORT:-18090}"
LOG="${TMPDIR:-/tmp}/live-infinita-cognitive-smoke.log"

export LIVE_COGNITIVE_HOST=127.0.0.1
export LIVE_COGNITIVE_PORT="$PORT"
export LIVE_COGNITIVE_AUTORUN=0

"$ROOT/deploy/server-cognitive-rc1/run.sh" >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null; then
    break
  fi
  sleep 0.1
done

curl -fsS "http://127.0.0.1:$PORT/health"
echo
curl -fsS -X POST -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$PORT/step"
echo
curl -fsS -X POST -H 'content-type: application/json' -d '{"count":3}' "http://127.0.0.1:$PORT/run"
echo
curl -fsS "http://127.0.0.1:$PORT/snapshot"
echo
curl -fsS "http://127.0.0.1:$PORT/soak"
echo

echo "Server Cognitive RC1 smoke: OK"
