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

# Recover stale backups accidentally left in sites-enabled by older installer versions.
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

# Add /audio/ to every server{} block for live.etbra.com.br, including the Certbot HTTPS block.
python3 - "$NGINX_CONF" <<'PY'
from pathlib import Path
import sys

p = Path(sys.argv[1])
s = p.read_text()
block = '''    location /audio/ {\n        proxy_pass http://127.0.0.1:8092/;\n        proxy_http_version 1.1;\n        proxy_buffering off;\n        proxy_cache off;\n        proxy_read_timeout 3600s;\n        add_header Cache-Control "no-store" always;\n    }\n\n'''

def server_ranges(text: str):
    out = []
    pos = 0
    while True:
        start = text.find('server {', pos)
        if start < 0:
            return out
        brace = text.find('{', start)
        depth = 0
        i = brace
        while i < len(text):
            if text[i] == '{':
                depth += 1
            elif text[i] == '}':
                depth -= 1
                if depth == 0:
                    out.append((start, i + 1))
                    pos = i + 1
                    break
            i += 1
        else:
            raise SystemExit('Bloco server nginx sem fechamento')

ranges = server_ranges(s)
replacements = []
for start, end in ranges:
    chunk = s[start:end]
    if 'server_name live.etbra.com.br;' not in chunk:
        continue
    if 'location /audio/' in chunk:
        continue
    # Insert before the first location in this server block; if absent, before closing brace.
    rel = chunk.find('    location ')
    if rel < 0:
        insert_at = end - 1
    else:
        insert_at = start + rel
    replacements.append(insert_at)

for insert_at in reversed(replacements):
    s = s[:insert_at] + block + s[insert_at:]

p.write_text(s)
print(f'Rotas /audio/ adicionadas em {len(replacements)} bloco(s) de live.etbra.com.br')
PY

if ! nginx -t; then
  cp -p "$backup" "$NGINX_CONF"
  nginx -t || true
  echo 'Configuração nginx restaurada após falha.' >&2
  exit 1
fi
systemctl reload nginx

bash "$SOURCE_DIR/deploy/install-godot-web.sh"

echo
echo 'Browser Audio instalado.'
echo 'Relay:  systemctl status live-infinita-audio-web --no-pager'
echo 'Health: curl -s http://127.0.0.1:8092/health'
echo 'Web:    https://live.etbra.com.br/audio/live.mp3'
echo 'Godot:  https://live.etbra.com.br/godot/'
echo 'No Edge, clique uma vez em ATIVAR ÁUDIO DA LIVE.'
