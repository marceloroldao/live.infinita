#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/marceloroldao/live.infinita.git"
BRANCH="mvp/ubuntu-prototype-001"
INSTALL_DIR="/opt/live.infinita"
SERVICE_USER="liveinfinita"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-ubuntu.sh"
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y git python3 python3-venv python3-pip nginx curl

if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home "$INSTALL_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
  git -C "$INSTALL_DIR" fetch origin "$BRANCH"
  git -C "$INSTALL_DIR" checkout "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
else
  rm -rf "$INSTALL_DIR"
  git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
fi

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/apps/world-runtime/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

install -m 0644 "$INSTALL_DIR/deploy/live-infinita.service" /etc/systemd/system/live-infinita.service
install -m 0644 "$INSTALL_DIR/deploy/nginx-live-infinita.conf" /etc/nginx/sites-available/live-infinita
ln -sf /etc/nginx/sites-available/live-infinita /etc/nginx/sites-enabled/live-infinita
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now live-infinita
systemctl enable --now nginx
systemctl restart nginx

sleep 1
curl --fail --silent http://127.0.0.1:8080/api/health >/dev/null

echo
printf 'Live Infinita MVP-001 instalado.\n'
printf 'Preview: http://IP_DA_VM/\n'
printf 'Health:  http://IP_DA_VM/api/health\n'
printf 'Status:  systemctl status live-infinita --no-pager\n'
