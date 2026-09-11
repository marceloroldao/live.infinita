#!/usr/bin/env bash
set -euo pipefail

GODOT_VERSION="4.7.2"
GODOT_TAG="${GODOT_VERSION}-stable"
GODOT_TEMPLATE_DIR_VERSION="${GODOT_VERSION}.stable"
INSTALL_ROOT="/opt/live-infinita-godot"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="$SOURCE_DIR/apps/renderer-godot"
WEB_DIR="/var/www/live-infinita-godot"
CACHE_DIR="/var/cache/live-infinita-godot"
ENGINE_ZIP="$CACHE_DIR/Godot_v${GODOT_TAG}_linux.x86_64.zip"
TEMPLATES_TPZ="$CACHE_DIR/Godot_v${GODOT_TAG}_export_templates.tpz"
ENGINE_URL="https://github.com/godotengine/godot/releases/download/${GODOT_TAG}/Godot_v${GODOT_TAG}_linux.x86_64.zip"
TEMPLATES_URL="https://github.com/godotengine/godot/releases/download/${GODOT_TAG}/Godot_v${GODOT_TAG}_export_templates.tpz"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-godot-web.sh"
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/project.godot" ]]; then
  echo "Erro: projeto Godot não encontrado em: $PROJECT_DIR"
  echo "Execute este script a partir de um checkout completo do repositório."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates libfontconfig1 fontconfig
mkdir -p "$INSTALL_ROOT" "$WEB_DIR" "$CACHE_DIR"

if [[ ! -f "$ENGINE_ZIP" ]]; then
  curl -fL "$ENGINE_URL" -o "$ENGINE_ZIP"
fi
if [[ ! -f "$TEMPLATES_TPZ" ]]; then
  curl -fL "$TEMPLATES_URL" -o "$TEMPLATES_TPZ"
fi

rm -rf "$INSTALL_ROOT/engine"
mkdir -p "$INSTALL_ROOT/engine"
unzip -q -o "$ENGINE_ZIP" -d "$INSTALL_ROOT/engine"
GODOT_BIN="$(find "$INSTALL_ROOT/engine" -maxdepth 1 -type f -name 'Godot_v*_linux.x86_64' | head -n1)"
chmod +x "$GODOT_BIN"

TEMPLATE_DIR="/root/.local/share/godot/export_templates/$GODOT_TEMPLATE_DIR_VERSION"
rm -rf "$TEMPLATE_DIR" /tmp/live-infinita-godot-templates
mkdir -p "$TEMPLATE_DIR" /tmp/live-infinita-godot-templates
unzip -q -o "$TEMPLATES_TPZ" -d /tmp/live-infinita-godot-templates
cp -a /tmp/live-infinita-godot-templates/templates/. "$TEMPLATE_DIR/"

rm -rf "$WEB_DIR"/*
"$GODOT_BIN" --headless --path "$PROJECT_DIR" --export-release "Web" "$WEB_DIR/index.html"

chown -R www-data:www-data "$WEB_DIR"
find "$WEB_DIR" -type d -exec chmod 0755 {} +
find "$WEB_DIR" -type f -exec chmod 0644 {} +

nginx -t
systemctl reload nginx

echo
echo "Godot ${GODOT_VERSION} Web exportado com sucesso."
echo "Projeto: $PROJECT_DIR"
echo "Abra: https://live.etbra.com.br/godot/"
