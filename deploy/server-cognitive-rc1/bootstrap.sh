#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENDOR="$ROOT/.vendor"
MEMORIA_SHA="45fdbe5b2404e00d40f492c2e503172a8eb22433"
BIT_SHA="2192c61e514a7bb500500ab9fff63bd42940dc52"

mkdir -p "$VENDOR" "$ROOT/var/server-cognitive-rc1"

checkout_pin() {
  local url="$1"
  local dir="$2"
  local sha="$3"

  if [[ ! -d "$dir/.git" ]]; then
    rm -rf "$dir"
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" remote add origin "$url"
  fi

  git -C "$dir" fetch --depth=1 origin "$sha"
  git -C "$dir" checkout --detach -q FETCH_HEAD

  local got
  got="$(git -C "$dir" rev-parse HEAD)"
  if [[ "$got" != "$sha" ]]; then
    echo "pin mismatch for $dir: expected=$sha got=$got" >&2
    exit 1
  fi
}

checkout_pin   "https://github.com/marceloroldao/memoria.ia.git"   "$VENDOR/memoria.ia"   "$MEMORIA_SHA"

checkout_pin   "https://github.com/marceloroldao/bit.analyze.git"   "$VENDOR/bit.analyze"   "$BIT_SHA"

export MEMORIA_IA_ROOT="$VENDOR/memoria.ia"
export BIT_ANALYZE_ROOT="$VENDOR/bit.analyze"

cd "$ROOT"
python3 - <<'PY'
import sys
from pathlib import Path

root = Path.cwd()
sys.path.insert(0, str(root / "apps" / "server-cognitive"))
from bootstrap_paths import configure_runtime_paths, MEMORIA_COMMIT, BIT_ANALYZE_COMMIT

paths = configure_runtime_paths()
from memoria_resolutiva.structural_context_admission_state_v2 import StructuralContextAdmissionStateMemory
from reality_slice import RealitySliceReorderBuffer

assert MEMORIA_COMMIT == "45fdbe5b2404e00d40f492c2e503172a8eb22433"
assert BIT_ANALYZE_COMMIT == "2192c61e514a7bb500500ab9fff63bd42940dc52"
assert StructuralContextAdmissionStateMemory is not None
assert RealitySliceReorderBuffer is not None
print("Server Cognitive RC1 dependencies: OK")
for key, value in paths.items():
    print(f"  {key}: {value}")
PY
