#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/live.infinita"
DATA_DIR="/var/lib/live-infinita"
SERVICE_USER="liveinfinita"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-ubuntu.sh"
  exit 1
fi

if [[ ! -f "$SOURCE_DIR/apps/world-runtime/main.py" ]]; then
  echo "Erro: execute o instalador a partir de um checkout completo do repositório."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip nginx curl rsync

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

mkdir -p "$INSTALL_DIR" "$DATA_DIR"
rsync -a --delete \
  --exclude '.git/' \
  --exclude '.venv/' \
  "$SOURCE_DIR/" "$INSTALL_DIR/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/apps/world-runtime/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" "$DATA_DIR"

install -m 0644 "$INSTALL_DIR/deploy/live-infinita.service" /etc/systemd/system/live-infinita.service
install -m 0644 "$INSTALL_DIR/deploy/nginx-live-infinita.conf" /etc/nginx/sites-available/live-infinita
ln -sf /etc/nginx/sites-available/live-infinita /etc/nginx/sites-enabled/live-infinita
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now live-infinita
systemctl enable --now nginx
systemctl restart live-infinita
systemctl restart nginx

sleep 1
curl --fail --silent http://127.0.0.1:8080/api/health >/dev/null

echo
printf 'Live Infinita MVP-004 instalado.\n'
printf 'Preview: http://IP_DA_VM/\n'
printf 'Health:  http://IP_DA_VM/api/health\n'
printf 'Gateway: http://IP_DA_VM/api/gateway/event\n'
printf 'Fontes:  http://IP_DA_VM/api/source/{source}/event\n'
printf 'Replay:  http://IP_DA_VM/api/replay/verify\n'
printf 'Dados:   /var/lib/live-infinita\n'
printf 'Status:  systemctl status live-infinita --no-pager\n'
