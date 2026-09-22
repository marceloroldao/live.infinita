#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if [[ ! -d "$ROOT/.vendor/memoria.ia/.git" || ! -d "$ROOT/.vendor/bit.analyze/.git" ]]; then
  echo "Missing pinned dependencies. Run:" >&2
  echo "  $ROOT/deploy/server-cognitive-rc1/bootstrap.sh" >&2
  exit 1
fi

export MEMORIA_IA_ROOT="${MEMORIA_IA_ROOT:-$ROOT/.vendor/memoria.ia}"
export BIT_ANALYZE_ROOT="${BIT_ANALYZE_ROOT:-$ROOT/.vendor/bit.analyze}"
export LIVE_COGNITIVE_HOST="${LIVE_COGNITIVE_HOST:-127.0.0.1}"
export LIVE_COGNITIVE_PORT="${LIVE_COGNITIVE_PORT:-8090}"
export LIVE_COGNITIVE_AUTORUN="${LIVE_COGNITIVE_AUTORUN:-1}"
export LIVE_COGNITIVE_STEP_SECONDS="${LIVE_COGNITIVE_STEP_SECONDS:-1.0}"
export LIVE_COGNITIVE_CHECKPOINT="${LIVE_COGNITIVE_CHECKPOINT:-$ROOT/var/server-cognitive-rc1/checkpoint.json}"
export LIVE_COGNITIVE_AUTOSAVE_EVERY="${LIVE_COGNITIVE_AUTOSAVE_EVERY:-10}"
export LIVE_COGNITIVE_RESUME="${LIVE_COGNITIVE_RESUME:-1}"

mkdir -p "$(dirname "$LIVE_COGNITIVE_CHECKPOINT")"

cd "$ROOT"
exec python3 apps/server-cognitive/server.py
