#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Execute: sudo bash deploy/prepare-broadcaster.sh'; exit 1; }

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL_DIR=/opt/live.infinita
BROADCASTER_DIR=$INSTALL_DIR/apps/broadcaster
UNIT=/etc/systemd/system/live-infinita-broadcaster.service
ENV_DIR=/etc/live-infinita
ENV_FILE=$ENV_DIR/broadcaster.env

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || { echo "Runtime não instalado em $INSTALL_DIR"; exit 1; }
[[ -f "$SOURCE_DIR/apps/broadcaster/broadcaster.py" ]] || { echo 'broadcaster.py ausente'; exit 1; }

mkdir -p "$BROADCASTER_DIR" "$ENV_DIR"
rsync -a --delete "$SOURCE_DIR/apps/broadcaster/" "$BROADCASTER_DIR/"
chown -R liveinfinita:liveinfinita "$BROADCASTER_DIR"
install -m 0644 "$SOURCE_DIR/deploy/live-infinita-broadcaster.service" "$UNIT"

if [[ ! -e "$ENV_FILE" ]]; then
  install -m 0600 /dev/null "$ENV_FILE"
  cat > "$ENV_FILE" <<'EOF'
# Live Infinita Broadcaster - intentionally disabled by default.
# Video and audio buses are local defaults (:5600 and :5500).
# Configure ONLY when ready to transmit:
# LIVE_INFINITA_STREAM_OUTPUT=rtmps://provider.example/app/STREAM_KEY
# LIVE_INFINITA_STREAM_WIDTH=1280
# LIVE_INFINITA_STREAM_HEIGHT=720
# LIVE_INFINITA_STREAM_FPS=30
# LIVE_INFINITA_VIDEO_BITRATE_KBPS=3500
# LIVE_INFINITA_AUDIO_BITRATE_KBPS=128
EOF
fi
chown root:liveinfinita "$ENV_FILE"
chmod 0640 "$ENV_FILE"

systemctl daemon-reload
systemctl disable live-infinita-broadcaster.service >/dev/null 2>&1 || true
systemctl stop live-infinita-broadcaster.service >/dev/null 2>&1 || true

echo 'Broadcaster preparado, mas DESABILITADO.'
echo "Configuração futura: $ENV_FILE"
echo 'Antes de habilitar, valide: sudo -u liveinfinita env $(grep -v "^#" /etc/live-infinita/broadcaster.env | xargs) /opt/live.infinita/.venv/bin/python /opt/live.infinita/apps/broadcaster/broadcaster.py --dry-run'
echo 'Nenhuma transmissão externa foi iniciada.'
