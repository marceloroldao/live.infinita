#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/live.infinita"
ENV_DIR="/etc/live-infinita"
ENV_FILE="$ENV_DIR/tiktok.env"
SERVICE="live-infinita-tiktok.service"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/configure-tiktok.sh @usuario"
  exit 1
fi

UNIQUE_ID="${1:-}"
if [[ -z "$UNIQUE_ID" ]]; then
  echo "Uso: sudo bash deploy/configure-tiktok.sh @usuario"
  exit 1
fi

if [[ "$UNIQUE_ID" != @* ]]; then
  UNIQUE_ID="@$UNIQUE_ID"
fi

if [[ ! -x "$INSTALL_DIR/.venv/bin/pip" ]]; then
  echo "Live Infinita não instalado em $INSTALL_DIR"
  exit 1
fi

"$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/apps/sources/requirements-tiktok.txt"

install -d -m 0750 -o root -g liveinfinita "$ENV_DIR"
cat > "$ENV_FILE" <<EOF
TIKTOK_UNIQUE_ID=$UNIQUE_ID
LIVE_INFINITA_TIKTOK_GATEWAY_URL=http://127.0.0.1:8080/api/source/tiktok/event
LIVE_INFINITA_SOURCE_TIMEOUT=5
EOF
chown root:liveinfinita "$ENV_FILE"
chmod 0640 "$ENV_FILE"

install -m 0644 "$INSTALL_DIR/deploy/live-infinita-tiktok.service" /etc/systemd/system/live-infinita-tiktok.service

systemctl daemon-reload
systemctl enable "$SERVICE"
systemctl restart "$SERVICE"

echo
printf 'TikTok Live Source configurado para %s.\n' "$UNIQUE_ID"
printf 'Config: %s\n' "$ENV_FILE"
printf 'Status: systemctl status %s --no-pager\n' "$SERVICE"
printf 'Logs:   journalctl -u %s -f\n' "$SERVICE"
