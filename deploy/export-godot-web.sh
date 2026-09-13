#!/usr/bin/env bash
set -Eeuo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/live.infinita}"
PROJECT_DIR="${PROJECT_DIR:-$INSTALL_DIR/apps/renderer-godot}"
WEB_DIR="${WEB_DIR:-/var/www/live-infinita-godot}"
ENGINE_ROOT="${GODOT_ENGINE_ROOT:-/opt/live-infinita-godot/engine}"
SOURCE_SHA="${LIVE_INFINITA_SOURCE_SHA:-unknown}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/export-godot-web.sh" >&2
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/project.godot" || ! -f "$PROJECT_DIR/export_presets.cfg" ]]; then
  echo "Projeto/export preset Godot não encontrado em $PROJECT_DIR" >&2
  exit 2
fi

GODOT_BIN="$(find "$ENGINE_ROOT" -maxdepth 1 -type f -name 'Godot_v*_linux.x86_64' -perm -u+x 2>/dev/null | sort | tail -n1 || true)"
if [[ -z "$GODOT_BIN" ]]; then
  echo "Godot instalado não encontrado em $ENGINE_ROOT" >&2
  echo "Instale uma vez com: sudo bash $INSTALL_DIR/deploy/install-godot-web.sh" >&2
  exit 3
fi

TMP_DIR="$(mktemp -d /tmp/live-infinita-godot-export.XXXXXX)"
cleanup(){ rm -rf "$TMP_DIR"; }
trap cleanup EXIT

printf '[godot] exportando projeto %s\n' "$PROJECT_DIR"
printf '[godot] engine: %s\n' "$GODOT_BIN"
"$GODOT_BIN" --headless --path "$PROJECT_DIR" --export-release "Web" "$TMP_DIR/index.html"

if [[ ! -s "$TMP_DIR/index.html" ]]; then
  echo "Export Godot não gerou index.html" >&2
  exit 4
fi

mkdir -p "$WEB_DIR"
rsync -a --delete "$TMP_DIR/" "$WEB_DIR/"

BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "$WEB_DIR/build.json" <<EOF
{
  "source_commit": "$SOURCE_SHA",
  "built_at": "$BUILD_TIME",
  "project": "Live Infinita Showcase",
  "renderer": "godot-web",
  "engine": "$(basename "$GODOT_BIN")"
}
EOF

chown -R www-data:www-data "$WEB_DIR"
find "$WEB_DIR" -type d -exec chmod 0755 {} +
find "$WEB_DIR" -type f -exec chmod 0644 {} +

if command -v nginx >/dev/null 2>&1; then
  nginx -t
  systemctl reload nginx
fi

printf '[godot] export publicado em %s (commit %s)\n' "$WEB_DIR" "$SOURCE_SHA"
