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
for required in nginx_godot_patch.py export-godot-web.sh; do
  [[ -f "$SOURCE_DIR/deploy/$required" ]] || {
    echo "Erro: deploy/$required não encontrado." >&2
    exit 1
  }
done

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y curl unzip ca-certificates libfontconfig1 fontconfig rsync
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
[[ -n "$GODOT_BIN" ]] || { echo 'Binário Godot não encontrado após extração.' >&2; exit 1; }
chmod +x "$GODOT_BIN"

TEMPLATE_DIR="/root/.local/share/godot/export_templates/$GODOT_TEMPLATE_DIR_VERSION"
rm -rf "$TEMPLATE_DIR" /tmp/live-infinita-godot-templates
mkdir -p "$TEMPLATE_DIR" /tmp/live-infinita-godot-templates
unzip -q -o "$TEMPLATES_TPZ" -d /tmp/live-infinita-godot-templates
cp -a /tmp/live-infinita-godot-templates/templates/. "$TEMPLATE_DIR/"

# O mesmo exportador usado pelos updates valida status, parse errors e publica
# atomicamente, preservando o build anterior quando o GDScript estiver inválido.
SOURCE_SHA="$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || printf unknown)"
env \
  INSTALL_DIR="$SOURCE_DIR" \
  PROJECT_DIR="$PROJECT_DIR" \
  WEB_DIR="$WEB_DIR" \
  GODOT_ENGINE_ROOT="$INSTALL_ROOT/engine" \
  LIVE_INFINITA_SOURCE_SHA="$SOURCE_SHA" \
  bash "$SOURCE_DIR/deploy/export-godot-web.sh"

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
echo "Commit:  $SOURCE_SHA"
echo "Abra: https://live.etbra.com.br/godot/"
