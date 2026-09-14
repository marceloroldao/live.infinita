#!/usr/bin/env bash
set -Eeuo pipefail

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
NGINX_BACKUP_DIR="/var/backups/live-infinita-nginx"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-godot-web.sh"
  exit 1
fi

if [[ ! -f "$PROJECT_DIR/project.godot" ]]; then
  echo "Erro: projeto Godot não encontrado em: $PROJECT_DIR"
  exit 1
fi
if [[ ! -f "$SOURCE_DIR/deploy/nginx_godot_patch.py" ]]; then
  echo "Erro: nginx_godot_patch.py não encontrado."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates libfontconfig1 fontconfig
mkdir -p "$INSTALL_ROOT" "$WEB_DIR" "$CACHE_DIR" "$NGINX_BACKUP_DIR"

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

STAGING_DIR="$(mktemp -d /tmp/live-infinita-godot-export.XXXXXX)"
cleanup(){ rm -rf "$STAGING_DIR"; }
trap cleanup EXIT

"$GODOT_BIN" --headless --path "$PROJECT_DIR" --export-release "Web" "$STAGING_DIR/index.html"
[[ -f "$STAGING_DIR/index.html" ]] || { echo 'Export Godot não gerou index.html.' >&2; exit 1; }

# Publica apenas depois de um export completo, evitando janela com build parcial.
rm -rf "$WEB_DIR"/*
cp -a "$STAGING_DIR"/. "$WEB_DIR"/
chown -R www-data:www-data "$WEB_DIR"
find "$WEB_DIR" -type d -exec chmod 0755 {} +
find "$WEB_DIR" -type f -exec chmod 0644 {} +

NGINX_ENTRY="$(grep -RIl 'server_name[[:space:]].*live\.etbra\.com\.br' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)"
if [[ -z "$NGINX_ENTRY" ]]; then
  echo 'Não encontrei o vhost live.etbra.com.br no nginx; export mantido, rota não alterada.' >&2
  exit 1
fi
NGINX_CONF="$(readlink -f "$NGINX_ENTRY")"
[[ -f "$NGINX_CONF" ]] || { echo "Vhost nginx inválido: $NGINX_ENTRY" >&2; exit 1; }
backup="$NGINX_BACKUP_DIR/$(basename "$NGINX_CONF").before-godot.$(date +%s)"
cp -p "$NGINX_CONF" "$backup"

rollback_nginx(){
  cp -p "$backup" "$NGINX_CONF"
  nginx -t >/dev/null 2>&1 || true
}

if ! python3 "$SOURCE_DIR/deploy/nginx_godot_patch.py" "$NGINX_CONF" live.etbra.com.br; then
  rollback_nginx
  echo 'Configuração nginx restaurada após falha no patch /godot/.' >&2
  exit 1
fi
if ! nginx -t; then
  rollback_nginx
  echo 'Configuração nginx restaurada após falha de validação.' >&2
  exit 1
fi
systemctl reload nginx

echo
echo "Godot ${GODOT_VERSION} Showcase exportado com sucesso."
echo "Projeto: $PROJECT_DIR"
echo "Abra: https://live.etbra.com.br/godot/"
