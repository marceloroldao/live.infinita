#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/live.infinita"
DATA_DIR="/var/lib/live-infinita"
ENV_DIR="/etc/live-infinita"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="liveinfinita"
MODEL_DIR="$DATA_DIR/audio/models"
PIPER_MODEL="$MODEL_DIR/pt_BR-faber-medium.onnx"
PIPER_CONFIG="$PIPER_MODEL.json"
PIPER_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium"
NATIVE_DIR="$DATA_DIR/audio/native-bin"
NATIVE_BIN="$NATIVE_DIR/live-infinita-audio-native"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-server-audio.sh"
  exit 1
fi

if [[ ! -f "$SOURCE_DIR/apps/audio-service/server_audio.py" ]]; then
  echo "Erro: checkout não contém apps/audio-service/server_audio.py"
  exit 1
fi
if [[ ! -f "$SOURCE_DIR/apps/audio-native/src/main.cpp" ]]; then
  echo "Erro: checkout não contém apps/audio-native/src/main.cpp"
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
DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg espeak-ng rsync curl ca-certificates g++

"$INSTALL_DIR/.venv/bin/pip" install --upgrade 'websockets>=15,<18' 'piper-tts>=1.3,<2'

mkdir -p "$INSTALL_DIR/apps/audio-service" "$INSTALL_DIR/apps/audio-native" "$DATA_DIR/audio/tts" "$MODEL_DIR" "$NATIVE_DIR" "$ENV_DIR"
rsync -a --delete "$SOURCE_DIR/apps/audio-service/" "$INSTALL_DIR/apps/audio-service/"
rsync -a --delete --exclude build/ "$SOURCE_DIR/apps/audio-native/" "$INSTALL_DIR/apps/audio-native/"
chown -R "$SERVICE_USER:$SERVICE_USER" "$NATIVE_DIR"
ROOT_DIR="$INSTALL_DIR" OUT_DIR="$NATIVE_DIR" sudo -u "$SERVICE_USER" bash "$SOURCE_DIR/deploy/build-native-audio.sh"

if [[ ! -s "$PIPER_MODEL" ]]; then
  echo "Baixando voz local Piper pt_BR-faber-medium (~63 MB)..."
  curl -fL "$PIPER_BASE/pt_BR-faber-medium.onnx?download=true" -o "$PIPER_MODEL"
fi
if [[ ! -s "$PIPER_CONFIG" ]]; then
  curl -fL "$PIPER_BASE/pt_BR-faber-medium.onnx.json?download=true" -o "$PIPER_CONFIG"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR/apps/audio-service" "$INSTALL_DIR/apps/audio-native" "$DATA_DIR/audio"
chmod 0750 "$DATA_DIR/audio"
chmod 0644 "$PIPER_MODEL" "$PIPER_CONFIG"

if [[ ! -f "$ENV_DIR/audio.env" ]]; then
  touch "$ENV_DIR/audio.env"
fi

# Remove legacy/cloud audio settings and values whose exact runtime path/sample
# rate must follow the current deploy. These are rewritten below, never merely
# appended, so old installations cannot pin the service to the former /opt build.
sed -i \
  '/^LIVE_INFINITA_TTS_MODEL=/d;
   /^LIVE_INFINITA_TTS_VOICE=/d;
   /^LIVE_INFINITA_TTS_INSTRUCTIONS=/d;
   /^LIVE_INFINITA_PIPER_/d;
   /^LIVE_INFINITA_AUDIO_SAMPLE_RATE=/d;
   /^LIVE_INFINITA_AUDIO_NATIVE_BIN=/d' \
  "$ENV_DIR/audio.env"

ensure_setting(){
  local setting="$1" key="${1%%=*}"
  if grep -q "^${key}=" "$ENV_DIR/audio.env"; then
    sed -i "s|^${key}=.*|${setting}|" "$ENV_DIR/audio.env"
  else
    echo "$setting" >> "$ENV_DIR/audio.env"
  fi
}

ensure_setting 'LIVE_INFINITA_WORLD_WS=ws://127.0.0.1:8080/ws'
ensure_setting 'LIVE_INFINITA_AUDIO_UDP=udp://127.0.0.1:5500?pkt_size=1316'
ensure_setting 'LIVE_INFINITA_AUDIO_SAMPLE_RATE=48000'
ensure_setting "LIVE_INFINITA_AUDIO_NATIVE_BIN=$NATIVE_BIN"
ensure_setting 'LIVE_INFINITA_PIPER_BIN=/opt/live.infinita/.venv/bin/piper'
ensure_setting 'LIVE_INFINITA_PIPER_MODEL=/var/lib/live-infinita/audio/models/pt_BR-faber-medium.onnx'
ensure_setting 'LIVE_INFINITA_AMBIENT_VOLUME=0.075'
ensure_setting 'LIVE_INFINITA_DUCKED_AMBIENT_VOLUME=0.025'
ensure_setting 'LIVE_INFINITA_RETRO_SCORE_VOLUME=0.10'
ensure_setting 'LIVE_INFINITA_NIGHT_INSECT_VOLUME=0.045'
ensure_setting 'LIVE_INFINITA_NARRATION_VOLUME=0.95'
chmod 0644 "$ENV_DIR/audio.env"

install -m 0644 "$SOURCE_DIR/deploy/live-infinita-audio.service" /etc/systemd/system/live-infinita-audio.service
systemctl daemon-reload
systemctl enable --now live-infinita-audio.service
systemctl restart live-infinita-audio.service
sleep 3

if ! systemctl is-active --quiet live-infinita-audio.service; then
  echo "Falha ao iniciar live-infinita-audio.service"
  systemctl status live-infinita-audio.service --no-pager || true
  exit 1
fi

if [[ -x "$NATIVE_BIN" ]]; then
  echo "Mixer realtime: C++ nativo 48 kHz / 20 ms ($NATIVE_BIN)"
else
  echo "AVISO: mixer C++ não foi compilado; serviço usará fallback Python."
fi

echo
echo "Server Audio LOCAL instalado."
echo "TTS principal: Piper pt_BR-faber-medium (local)"
echo "Fallback: espeak-ng pt-br (local)"
echo "Ambiente: procedural local com DSP C++ nativo"
echo "OpenAI para áudio: DESATIVADA"
echo "Status:  systemctl status live-infinita-audio --no-pager"
echo "Logs:    journalctl -u live-infinita-audio -f"
echo "Estado:  $DATA_DIR/audio/status.json"
echo "Eventos: $DATA_DIR/audio/narration-events.jsonl"
echo "Bus:     udp://127.0.0.1:5500 (MPEG-TS/AAC 48 kHz stereo)"
