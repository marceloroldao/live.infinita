#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/live.infinita"
DATA_DIR="/var/lib/live-infinita"
ENV_DIR="/etc/live-infinita"
OPERATOR_ENV="$ENV_DIR/operator.env"
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
rsync -a --delete --exclude '.git/' --exclude '.venv/' "$SOURCE_DIR/" "$INSTALL_DIR/"

python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/apps/world-runtime/requirements.txt"

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR" "$DATA_DIR"
install -d -m 0750 -o root -g "$SERVICE_USER" "$ENV_DIR"
if [[ ! -f "$OPERATOR_ENV" ]]; then
  OPERATOR_TOKEN="$("$INSTALL_DIR/.venv/bin/python" -c 'import secrets; print(secrets.token_hex(32))')"
  install -o root -g root -m 0600 /dev/null "$OPERATOR_ENV"
  printf 'LIVE_INFINITA_OPERATOR_TOKEN=%s\n' "$OPERATOR_TOKEN" > "$OPERATOR_ENV"
fi
install -d -m 0755 /etc/systemd/system/live-infinita.service.d
printf '[Service]\nEnvironmentFile=%s\n' "$OPERATOR_ENV" > /etc/systemd/system/live-infinita.service.d/009-actor-operator.conf
install -m 0644 "$INSTALL_DIR/deploy/live-infinita.service" /etc/systemd/system/live-infinita.service
install -m 0644 "$INSTALL_DIR/deploy/live-infinita-tiktok.service" /etc/systemd/system/live-infinita-tiktok.service
install -m 0644 "$INSTALL_DIR/deploy/live-infinita-integrations.path" /etc/systemd/system/live-infinita-integrations.path
install -m 0644 "$INSTALL_DIR/deploy/live-infinita-integrations-reload.service" /etc/systemd/system/live-infinita-integrations-reload.service
install -m 0644 "$INSTALL_DIR/deploy/nginx-live-infinita.conf" /etc/nginx/sites-available/live-infinita
ln -sf /etc/nginx/sites-available/live-infinita /etc/nginx/sites-enabled/live-infinita
rm -f /etc/nginx/sites-enabled/default

nginx -t
systemctl daemon-reload
systemctl enable --now live-infinita
systemctl enable --now live-infinita-integrations.path
systemctl enable --now nginx
systemctl restart live-infinita
systemctl restart nginx

sleep 1
curl --fail --silent http://127.0.0.1:8080/api/health >/dev/null

echo
printf 'Live Infinita MVP-012 instalado.\n'
printf 'Preview:       http://IP_DA_VM/\n'
printf 'Gerência:      http://IP_DA_VM/manage/\n'
printf 'Health:        http://IP_DA_VM/api/health\n'
printf 'Actors:        http://IP_DA_VM/api/actors\n'
printf 'Audience:      http://IP_DA_VM/api/audience/events\n'
printf 'Audience PR:   http://IP_DA_VM/api/audience/proposals\n'
printf 'AI Context:    POST http://IP_DA_VM/api/ai/context/preview\n'
printf 'AI Proposals:  http://IP_DA_VM/api/ai/proposals\n'
printf 'Replay:        http://IP_DA_VM/api/replay/verify\n'
printf 'TikTok:        opcional; configure com sudo bash deploy/configure-tiktok.sh @usuario\n'
printf 'Dados:         /var/lib/live-infinita\n'
printf 'Status:        systemctl status live-infinita --no-pager\n'
printf 'Chave:         sudo sed -n '\''s/^LIVE_INFINITA_OPERATOR_TOKEN=//p'\'' %s\n' "$OPERATOR_ENV"
