#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/live.infinita"
DATA_DIR="/var/lib/live-infinita"
ENV_DIR="/etc/live-infinita"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="liveinfinita"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-server-audio.sh"
  exit 1
fi

if [[ ! -f "$SOURCE_DIR/apps/audio-service/server_audio.py" ]]; then
  echo "Erro: checkout não contém apps/audio-service/server_audio.py"
  exit 1
fi
if [[ ! -x "$INSTALL_DIR/.venv/bin/python" ]]; then
  echo "Erro: Live Infinita principal não está instalado em $INSTALL_DIR"
  exit 1
fi
if ! id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Erro: usuário $SERVICE_USER não existe; instale primeiro o runtime principal."
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg espeak-ng rsync

"$INSTALL_DIR/.venv/bin/pip" install --upgrade 'websockets>=15,<18'

mkdir -p "$INSTALL_DIR/apps/audio-service" "$DATA_DIR/audio/tts" "$ENV_DIR"
rsync -a --delete "$SOURCE_DIR/apps/audio-service/" "$INSTALL_DIR/apps/audio-service/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/apps/audio-service" "$DATA_DIR/audio"
chmod 0750 "$DATA_DIR/audio"

if [[ ! -f "$ENV_DIR/audio.env" ]]; then
  cat > "$ENV_DIR/audio.env" <<'EOF'
LIVE_INFINITA_WORLD_WS=ws://127.0.0.1:8080/ws
LIVE_INFINITA_AUDIO_UDP=udp://127.0.0.1:5500?pkt_size=1316
LIVE_INFINITA_AUDIO_SAMPLE_RATE=48000
LIVE_INFINITA_TTS_MODEL=gpt-4o-mini-tts
LIVE_INFINITA_TTS_VOICE=alloy
LIVE_INFINITA_AMBIENT_VOLUME=0.075
LIVE_INFINITA_DUCKED_AMBIENT_VOLUME=0.025
LIVE_INFINITA_NARRATION_VOLUME=0.95
EOF
  chmod 0644 "$ENV_DIR/audio.env"
fi

install -m 0644 "$SOURCE_DIR/deploy/live-infinita-audio.service" /etc/systemd/system/live-infinita-audio.service
systemctl daemon-reload
systemctl enable --now live-infinita-audio.service
systemctl restart live-infinita-audio.service
sleep 2

if ! systemctl is-active --quiet live-infinita-audio.service; then
  echo "Falha ao iniciar live-infinita-audio.service"
  systemctl status live-infinita-audio.service --no-pager || true
  exit 1
fi

echo
echo "Server Audio instalado."
echo "Status:  systemctl status live-infinita-audio --no-pager"
echo "Logs:    journalctl -u live-infinita-audio -f"
echo "Estado:  $DATA_DIR/audio/status.json"
echo "Eventos: $DATA_DIR/audio/narration-events.jsonl"
echo "Bus:     udp://127.0.0.1:5500 (MPEG-TS/AAC 48 kHz stereo)"
echo "Teste:   ffplay -nodisp -autoexit udp://127.0.0.1:5500"
