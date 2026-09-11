#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/install-web-log-console.sh'; exit 1; }
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR=/opt/live.infinita
MANAGER_DIR="$INSTALL_DIR/apps/manager"
LOG_DIR="$INSTALL_DIR/apps/ops-log-service"
NGINX_SITE=/etc/nginx/sites-available/live-infinita
UNIT=/etc/systemd/system/live-infinita-ops-logs.service

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || { echo "Runtime principal não encontrado em $INSTALL_DIR"; exit 1; }
id liveinfinita >/dev/null 2>&1 || { echo 'Usuário liveinfinita não existe.'; exit 1; }
getent group systemd-journal >/dev/null || { echo 'Grupo systemd-journal não existe nesta VM.'; exit 1; }

backup=$(mktemp -d /var/backups/live-infinita-web-logs.XXXXXX)
chmod 700 "$backup"
echo "Backup: $backup"
cp -a "$MANAGER_DIR" "$backup/manager"
cp -p "$NGINX_SITE" "$backup/nginx-live-infinita.conf"
[[ ! -f "$UNIT" ]] || cp -p "$UNIT" "$backup/live-infinita-ops-logs.service"

install -d -o liveinfinita -g liveinfinita -m 0755 "$LOG_DIR"
install -o liveinfinita -g liveinfinita -m 0644 "$SOURCE_DIR/apps/ops-log-service/log_service.py" "$LOG_DIR/log_service.py"
install -o liveinfinita -g liveinfinita -m 0644 "$SOURCE_DIR/apps/manager/index.html" "$MANAGER_DIR/index.html"
install -o liveinfinita -g liveinfinita -m 0644 "$SOURCE_DIR/apps/manager/app.js" "$MANAGER_DIR/app.js"
install -o liveinfinita -g liveinfinita -m 0644 "$SOURCE_DIR/apps/manager/monitoring.css" "$MANAGER_DIR/monitoring.css"
install -o root -g root -m 0644 "$SOURCE_DIR/deploy/live-infinita-ops-logs.service" "$UNIT"
install -o root -g root -m 0644 "$SOURCE_DIR/deploy/nginx-live-infinita.conf" "$NGINX_SITE"
ln -sf "$NGINX_SITE" /etc/nginx/sites-enabled/live-infinita

systemctl daemon-reload
systemctl enable --now live-infinita-ops-logs.service
systemctl restart live-infinita-ops-logs.service
nginx -t
systemctl reload nginx
sleep 1

systemctl is-active --quiet live-infinita-ops-logs.service
curl --fail --silent 'http://127.0.0.1:8091/api/ops/logs/tiktok?lines=20' >/dev/null
curl --fail --silent 'http://127.0.0.1:8091/api/ops/logs/audio?lines=20' >/dev/null

echo
echo 'Console web de logs instalado.'
echo 'Abra o Manager -> Visão geral -> Logs em tempo real.'
echo 'TikTok:   live-infinita-tiktok.service'
echo 'Narrador: live-infinita-audio.service'
echo 'O backend de logs escuta somente em 127.0.0.1:8091 e o Nginx exige sessão do Manager.'
