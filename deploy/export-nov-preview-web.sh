#!/usr/bin/env bash
# Publish the optional Nov 3D preview below the existing /godot/ location.
# Does not restart services, edit nginx, replace the broadcast export, or write World State.
set -Eeuo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SOURCE_DIR/apps/renderer-godot}"
WEB_ROOT="${WEB_ROOT:-/var/www/live-infinita-godot}"
ENGINE_ROOT="${GODOT_ENGINE_ROOT:-/opt/live-infinita-godot/engine}"
PREVIEW_NAME="nov-preview"
SOURCE_SHA="${LIVE_INFINITA_SOURCE_SHA:-$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/export-nov-preview-web.sh" >&2
  exit 1
fi

for required in "$PROJECT_DIR/project.godot" "$PROJECT_DIR/export_presets.cfg" "$PROJECT_DIR/nov_character_preview.tscn" "$PROJECT_DIR/nov_character_visual.gd"; do
  if [[ ! -f "$required" ]]; then
    echo "Arquivo Godot ausente: $required" >&2
    exit 2
  fi
done

# This directory must already be served by the existing nginx /godot/ alias.
# Do not silently create a separate non-public directory or modify production.
if [[ ! -s "$WEB_ROOT/index.html" ]]; then
  echo "Export principal ausente em $WEB_ROOT; configure /godot/ antes de instalar a prévia." >&2
  exit 3
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "Instale rsync primeiro (sudo apt-get install rsync)." >&2
  exit 4
fi

GODOT_BIN="$(find "$ENGINE_ROOT" -maxdepth 1 -type f -name 'Godot_v*_linux.x86_64' -perm -u+x 2>/dev/null | sort | tail -n1 || true)"
if [[ -z "$GODOT_BIN" ]]; then
  echo "Engine Godot Web não instalada em $ENGINE_ROOT." >&2
  echo "Primeira instalação: sudo bash deploy/install-godot-web.sh" >&2
  exit 5
fi

TEMP_ROOT="$(mktemp -d /tmp/live-infinita-nov-web.XXXXXX)"
STAGE=""
BACKUP=""
cleanup() {
  [[ -z "$STAGE" || ! -d "$STAGE" ]] || rm -rf -- "$STAGE"
  rm -rf -- "$TEMP_ROOT"
}
trap cleanup EXIT

WORK_PROJECT="$TEMP_ROOT/renderer-godot"
BUILD_DIR="$TEMP_ROOT/export"
mkdir -p "$WORK_PROJECT" "$BUILD_DIR"

# Never change source project.godot (main.tscn stays the broadcast scene).
rsync -a --exclude '/.godot/' --exclude 'build/' "$PROJECT_DIR/" "$WORK_PROJECT/"
python3 - "$WORK_PROJECT/project.godot" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8")
production = 'run/main_scene="res://main.tscn"'
preview = 'run/main_scene="res://nov_character_preview.tscn"'
if raw.count(production) != 1:
    raise SystemExit("Cena principal inesperada; prévia não publicada.")
path.write_text(raw.replace(production, preview, 1), encoding="utf-8")
PY

# Import glTF into the isolated project before exporting the scene.
IMPORT_LOG="$TEMP_ROOT/import.log"
EXPORT_LOG="$TEMP_ROOT/export.log"
echo "[nov-preview] Importando recursos em cópia isolada."
set +e
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT_BIN" --headless --editor --quit --path "$WORK_PROJECT" >"$IMPORT_LOG" 2>&1
IMPORT_STATUS=$?
set -e
if ((IMPORT_STATUS != 0)) || grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$IMPORT_LOG"; then
  cat "$IMPORT_LOG" >&2
  echo "Falha no import Godot; transmissão atual preservada." >&2
  exit 6
fi

echo "[nov-preview] Exportando Web em diretório temporário."
set +e
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT_BIN" --headless --path "$WORK_PROJECT" --export-release "Web" "$BUILD_DIR/index.html" >"$EXPORT_LOG" 2>&1
EXPORT_STATUS=$?
set -e
if ((EXPORT_STATUS != 0)) || grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$EXPORT_LOG"; then
  cat "$EXPORT_LOG" >&2
  echo "Falha no export Godot; transmissão atual preservada." >&2
  exit 7
fi
if [[ ! -s "$BUILD_DIR/index.html" ]] ||
   ! find "$BUILD_DIR" -maxdepth 1 -type f -name '*.wasm' -size +0c -print -quit | grep -q . ||
   ! find "$BUILD_DIR" -maxdepth 1 -type f -name '*.pck' -size +0c -print -quit | grep -q .; then
  echo "Export Web incompleto (index.html / wasm / pck ausente)." >&2
  exit 8
fi

cat >"$BUILD_DIR/build.json" <<EOF
{
  "source_commit": "$SOURCE_SHA",
  "project": "Live Infinita - Nov visual preview",
  "scene": "res://nov_character_preview.tscn",
  "renderer": "godot-web",
  "skin": "placeholder-until-official-standard-body-is-imported"
}
EOF

# Atomic replacement of preview subfolder only. Existing /godot/index.* untouched.
STAGE="$(mktemp -d "$WEB_ROOT/.nov-preview.stage.XXXXXX")"
rsync -a "$BUILD_DIR/" "$STAGE/"
chown -R www-data:www-data "$STAGE"
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +

TARGET="$WEB_ROOT/$PREVIEW_NAME"
if [[ -e "$TARGET" && ! -d "$TARGET" ]]; then
  echo "Destino ocupado por arquivo: $TARGET" >&2
  exit 9
fi
if [[ -d "$TARGET" ]]; then
  BACKUP="$WEB_ROOT/.nov-preview.previous.$$"
  mv -- "$TARGET" "$BACKUP"
fi
if ! mv -- "$STAGE" "$TARGET"; then
  if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
    mv -- "$BACKUP" "$TARGET"
  fi
  echo "Falha ao publicar; prévia anterior restaurada." >&2
  exit 10
fi
STAGE=""
[[ -z "$BACKUP" ]] || rm -rf -- "$BACKUP"

echo "[nov-preview] Publicação concluída: $TARGET"
echo "[nov-preview] Abra https://live.etbra.com.br/godot/nov-preview/"
echo "[nov-preview] A live 2D /godot/ e o mundo persistente não foram alterados."
