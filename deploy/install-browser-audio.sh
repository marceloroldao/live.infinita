#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Execute: sudo bash deploy/install-browser-audio.sh'; exit 1; }

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL_DIR=/opt/live.infinita
BRIDGE_DIR=$INSTALL_DIR/apps/audio-web-bridge
UNIT=/etc/systemd/system/live-infinita-audio-web.service
NGINX_BACKUP_DIR=/var/backups/live-infinita-nginx

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || { echo "Runtime não instalado em $INSTALL_DIR"; exit 1; }
[[ -f "$SOURCE_DIR/apps/audio-web-bridge/audio_web_bridge.py" ]] || { echo 'audio_web_bridge.py ausente'; exit 1; }
[[ -f "$SOURCE_DIR/deploy/nginx_audio_patch.py" ]] || { echo 'nginx_audio_patch.py ausente'; exit 1; }
[[ -f "$SOURCE_DIR/deploy/nginx_monitor_patch.py" ]] || { echo 'nginx_monitor_patch.py ausente'; exit 1; }
systemctl is-active --quiet live-infinita-audio || { echo 'live-infinita-audio precisa estar ativo'; exit 1; }

mkdir -p "$BRIDGE_DIR" "$NGINX_BACKUP_DIR"
rsync -a --delete "$SOURCE_DIR/apps/audio-web-bridge/" "$BRIDGE_DIR/"
chown -R liveinfinita:liveinfinita "$BRIDGE_DIR"
install -m 0644 "$SOURCE_DIR/deploy/live-infinita-audio-web.service" "$UNIT"
systemctl daemon-reload
systemctl enable --now live-infinita-audio-web.service
systemctl restart live-infinita-audio-web.service

for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8092/health >/dev/null 2>&1; then break; fi
  sleep .5
done
curl -fsS http://127.0.0.1:8092/health >/dev/null || {
  systemctl status live-infinita-audio-web --no-pager || true
  journalctl -u live-infinita-audio-web -n 50 --no-pager || true
  exit 1
}

while IFS= read -r stale_backup; do
  [[ -n "$stale_backup" ]] || continue
  mv "$stale_backup" "$NGINX_BACKUP_DIR/$(basename "$stale_backup")"
done < <(find /etc/nginx/sites-enabled -maxdepth 1 -type f -name 'live-infinita.before-audio.*' -print 2>/dev/null)

NGINX_ENTRY=$(grep -RIl 'server_name[[:space:]].*live\.etbra\.com\.br' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)
[[ -n "$NGINX_ENTRY" ]] || { echo 'Não encontrei o vhost live.etbra.com.br no nginx.'; exit 1; }
NGINX_CONF=$(readlink -f "$NGINX_ENTRY")
[[ -f "$NGINX_CONF" ]] || { echo "Vhost nginx inválido: $NGINX_ENTRY"; exit 1; }

backup="$NGINX_BACKUP_DIR/$(basename "$NGINX_CONF").before-audio.$(date +%s)"
cp -p "$NGINX_CONF" "$backup"

if ! python3 "$SOURCE_DIR/deploy/nginx_audio_patch.py" "$NGINX_CONF" live.etbra.com.br; then
  cp -p "$backup" "$NGINX_CONF"
  echo 'Configuração nginx restaurada após falha no patch de áudio.' >&2
  exit 1
fi
if ! python3 "$SOURCE_DIR/deploy/nginx_monitor_patch.py" "$NGINX_CONF" live.etbra.com.br; then
  cp -p "$backup" "$NGINX_CONF"
  echo 'Configuração nginx restaurada após falha no patch do monitor.' >&2
  exit 1
fi

if ! nginx -t; then
  cp -p "$backup" "$NGINX_CONF"
  nginx -t || true
  echo 'Configuração nginx restaurada após falha.' >&2
  exit 1
fi
systemctl reload nginx

bash "$SOURCE_DIR/deploy/install-godot-web.sh"

echo
echo 'Browser Audio + Live Monitor instalados.'
echo 'Relay:   systemctl status live-infinita-audio-web --no-pager'
echo 'Health:  curl -s http://127.0.0.1:8092/health'
echo 'Monitor: https://live.etbra.com.br/monitor/'
echo 'Godot:   https://live.etbra.com.br/godot/'
