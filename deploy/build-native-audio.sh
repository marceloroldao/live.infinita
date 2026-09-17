#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
SRC="$ROOT_DIR/apps/audio-native/src/main.cpp"
OUT_DIR="${OUT_DIR:-$ROOT_DIR/apps/audio-native/build}"
OUT="$OUT_DIR/live-infinita-audio-native"

if [[ ! -f "$SRC" ]]; then
  echo "[audio-native] source ausente: $SRC"
  exit 0
fi

CXX="${CXX:-g++}"
if ! command -v "$CXX" >/dev/null 2>&1; then
  echo "[audio-native] compilador C++ não encontrado; mixer Python continuará como fallback."
  exit 0
fi

mkdir -p "$OUT_DIR"
if [[ -x "$OUT" && "$OUT" -nt "$SRC" ]]; then
  echo "[audio-native] binário já está atualizado: $OUT"
  exit 0
fi

echo "[audio-native] compilando hot loop DSP C++..."
"$CXX" -std=c++20 -O3 -DNDEBUG -pthread -Wall -Wextra -Wpedantic "$SRC" -o "$OUT.tmp"
mv "$OUT.tmp" "$OUT"
chmod 0755 "$OUT"
echo "[audio-native] pronto: $OUT"
