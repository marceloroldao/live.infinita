#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PORT="${LIVE_COGNITIVE_SMOKE_PORT:-18090}"
LOG="${TMPDIR:-/tmp}/live-infinita-cognitive-smoke.log"
CHECKPOINT="${TMPDIR:-/tmp}/live-infinita-cognitive-smoke-checkpoint.json"

export LIVE_COGNITIVE_HOST=127.0.0.1
export LIVE_COGNITIVE_PORT="$PORT"
export LIVE_COGNITIVE_AUTORUN=0
export LIVE_COGNITIVE_CHECKPOINT="$CHECKPOINT"
export LIVE_COGNITIVE_AUTOSAVE_EVERY=2
export LIVE_COGNITIVE_RESUME=1

rm -f "$CHECKPOINT"

PID=""

stop_server() {
  if [[ -n "${PID:-}" ]]; then
    kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
    PID=""
  fi
}

start_server() {
  "$ROOT/deploy/server-cognitive-rc1/run.sh" >"$LOG" 2>&1 &
  PID=$!
  for _ in $(seq 1 80); do
    if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null; then
      return 0
    fi
    sleep 0.1
  done
  echo "Server Cognitive RC1 did not become healthy" >&2
  cat "$LOG" >&2 || true
  return 1
}

trap 'stop_server; rm -f "$CHECKPOINT"' EXIT

start_server

curl -fsS "http://127.0.0.1:$PORT/health"
echo
curl -fsS -X POST -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$PORT/step"
echo
curl -fsS -X POST -H 'content-type: application/json' -d '{"count":3}' "http://127.0.0.1:$PORT/run"
echo
curl -fsS -X POST -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$PORT/checkpoint"
echo

BEFORE="$(curl -fsS "http://127.0.0.1:$PORT/snapshot")"
BEFORE_CYCLE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["cycle_id"])' <<<"$BEFORE")"

stop_server
start_server

AFTER="$(curl -fsS "http://127.0.0.1:$PORT/snapshot")"
AFTER_CYCLE="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["cycle_id"])' <<<"$AFTER")"
LOADED="$(python3 -c 'import json,sys; print(str(json.load(sys.stdin)["service"]["loaded_from_checkpoint"]).lower())' <<<"$AFTER")"

if [[ "$AFTER_CYCLE" != "$BEFORE_CYCLE" ]]; then
  echo "checkpoint restart mismatch: before=$BEFORE_CYCLE after=$AFTER_CYCLE" >&2
  exit 1
fi
if [[ "$LOADED" != "true" ]]; then
  echo "server did not report loaded_from_checkpoint=true" >&2
  exit 1
fi

curl -fsS -X POST -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$PORT/step"
echo
curl -fsS "http://127.0.0.1:$PORT/soak"
echo

echo "Server Cognitive RC1 smoke + restart: OK"
