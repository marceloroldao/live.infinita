#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute como root: sudo bash deploy/install-live-showcase.sh"
  exit 1
fi

printf '\n[1/4] Verificando runtime...\n'
HEALTH="$(curl --fail --silent http://127.0.0.1:8080/api/health)" || {
  echo "Runtime Live Infinita não respondeu em 127.0.0.1:8080"
  exit 1
}
printf '%s\n' "$HEALTH"

printf '\n[2/4] Instalando Server Audio...\n'
bash "$SOURCE_DIR/deploy/install-server-audio.sh"

printf '\n[3/4] Exportando Godot Showcase...\n'
bash "$SOURCE_DIR/deploy/install-godot-web.sh"

printf '\n[4/4] Conferindo serviços...\n'
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-audio.service
curl --fail --silent http://127.0.0.1:8080/api/replay/verify
printf '\n'

printf '\nLive Infinita Showcase instalada.\n'
printf 'Tela:      https://live.etbra.com.br/godot/\n'
printf 'Runtime:   systemctl status live-infinita --no-pager\n'
printf 'Narrador:  systemctl status live-infinita-audio --no-pager\n'
printf 'Audio log: journalctl -u live-infinita-audio -f\n'
printf 'TikTok:    journalctl -u live-infinita-tiktok -f\n'
printf 'Replay:    curl -s http://127.0.0.1:8080/api/replay/verify\n'
printf '\nO Godot é apenas apresentação. Narrativa/áudio são controlados pelo servidor.\n'
