#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-live-showcase.sh"
  exit 1
fi

printf '\n[1/5] Verificando runtime...\n'
HEALTH="$(curl --fail --silent http://127.0.0.1:8080/api/health)" || {
  echo "Runtime Live Infinita não respondeu em 127.0.0.1:8080"
  exit 1
}
printf '%s\n' "$HEALTH"

printf '\n[2/5] Instalando Server Audio...\n'
bash "$SOURCE_DIR/deploy/install-server-audio.sh"

printf '\n[3/5] Instalando Browser Audio e exportando Godot Showcase...\n'
bash "$SOURCE_DIR/deploy/install-browser-audio.sh"

printf '\n[4/5] Instalando renderer Godot nativo server-side...\n'
bash "$SOURCE_DIR/deploy/install-headless-renderer.sh"

printf '\n[5/5] Conferindo serviços e invariantes...\n'
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-audio.service
systemctl is-active --quiet live-infinita-audio-web.service
systemctl is-active --quiet live-infinita-renderer.service
curl --fail --silent http://127.0.0.1:8092/health
printf '\n'
curl --fail --silent http://127.0.0.1:8080/api/replay/verify
printf '\n'

printf '\nLive Infinita Showcase instalada.\n'
printf 'Tela web:    https://live.etbra.com.br/godot/\n'
printf 'Áudio web:   https://live.etbra.com.br/audio/live.mp3\n'
printf 'Runtime:     systemctl status live-infinita --no-pager\n'
printf 'Narrador:    systemctl status live-infinita-audio --no-pager\n'
printf 'Relay web:   systemctl status live-infinita-audio-web --no-pager\n'
printf 'Renderer:    systemctl status live-infinita-renderer --no-pager\n'
printf 'Video bus:   udp://127.0.0.1:5600\n'
printf 'Audio bus:   udp://127.0.0.1:5500\n'
printf 'Broadcaster: python apps/broadcaster/broadcaster.py --probe\n'
printf 'TikTok:      journalctl -u live-infinita-tiktok -f\n'
printf 'Replay:      curl -s http://127.0.0.1:8080/api/replay/verify\n'
printf '\nBroadcaster externo permanece desativado até configuração explícita de LIVE_INFINITA_STREAM_OUTPUT.\n'
printf 'Godot é projeção; World State continua sendo a autoridade.\n'
