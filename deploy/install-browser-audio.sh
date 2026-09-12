#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Execute: sudo bash deploy/install-browser-audio.sh'; exit 1; }

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL_DIR=/opt/live.infinita
BRIDGE_DIR=$INSTALL_DIR/apps/audio-web-bridge
UNIT=/etc/systemd/system/live-infinita-audio-web.service

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || { echo "Runtime não instalado em $INSTALL_DIR"; exit 1; }
[[ -f "$SOURCE_DIR/apps/audio-web-bridge/audio_web_bridge.py" ]] || { echo 'audio_web_bridge.py ausente'; exit 1; }
systemctl is-active --quiet live-infinita-audio || { echo 'live-infinita-audio precisa estar ativo'; exit 1; }

mkdir -p "$BRIDGE_DIR"
rsync -a --delete "$SOURCE_DIR/apps/audio-web-bridge/" "$BRIDGE_DIR/"
chown -R liveinfinita:liveinfinita "$BRIDGE_DIR"
install -m 0644 "$SOURCE_DIR/deploy/live-infinita-audio-web.service" "$UNIT"
systemctl daemon-reload
systemctl enable --now live-infinita-audio-web.service
systemctl restart live-infinita-audio-web.service

for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8092/health >/dev/null; then break; fi
  sleep .5
done
curl -fsS http://127.0.0.1:8092/health >/dev/null || {
  systemctl status live-infinita-audio-web --no-pager || true
  exit 1
}

NGINX_CONF=$(grep -RIl --include='*.conf' 'server_name[[:space:]].*live\.etbra\.com\.br' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)
if [[ -z "$NGINX_CONF" ]]; then
  NGINX_CONF=$(grep -RIl 'server_name[[:space:]].*live\.etbra\.com\.br' /etc/nginx/sites-enabled /etc/nginx/conf.d 2>/dev/null | head -n1 || true)
fi
[[ -n "$NGINX_CONF" ]] || { echo 'Não encontrei o vhost live.etbra.com.br no nginx.'; exit 1; }

if ! grep -q 'location /audio/' "$NGINX_CONF"; then
  backup="${NGINX_CONF}.before-audio.$(date +%s)"
  cp -p "$NGINX_CONF" "$backup"
  python3 - "$NGINX_CONF" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
s=p.read_text()
needle='    location / {\n'
block='''    location /audio/ {\n        proxy_pass http://127.0.0.1:8092/;\n        proxy_http_version 1.1;\n        proxy_buffering off;\n        proxy_cache off;\n        proxy_read_timeout 3600s;\n        add_header Cache-Control "no-store" always;\n    }\n\n'''
if needle not in s:
    raise SystemExit('Não encontrei location / { para inserir a rota de áudio')
s=s.replace(needle, block+needle)
p.write_text(s)
PY
  if ! nginx -t; then
    cp -p "$backup" "$NGINX_CONF"
    nginx -t
    echo 'Configuração nginx restaurada após falha.' >&2
    exit 1
  fi
  systemctl reload nginx
fi

bash "$SOURCE_DIR/deploy/install-godot-web.sh"

echo
echo 'Browser Audio instalado.'
echo 'Relay:  systemctl status live-infinita-audio-web --no-pager'
echo 'Health: curl -s http://127.0.0.1:8092/health'
echo 'Web:    https://live.etbra.com.br/audio/live.mp3'
echo 'Godot:  https://live.etbra.com.br/godot/'
echo 'No Edge, clique uma vez em ATIVAR ÁUDIO DA LIVE.'
