#!/usr/bin/env bash
set -Eeuo pipefail

[[ $EUID -eq 0 ]] || { echo 'Execute: sudo bash deploy/install-headless-renderer.sh'; exit 1; }

SOURCE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
INSTALL_DIR=/opt/live.infinita
RENDERER_DIR=$INSTALL_DIR/apps/headless-renderer
GODOT_BIN=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
UNIT=/etc/systemd/system/live-infinita-renderer.service

[[ -x "$INSTALL_DIR/.venv/bin/python" ]] || { echo "Runtime não instalado em $INSTALL_DIR"; exit 1; }
[[ -x "$GODOT_BIN" ]] || { echo "Godot nativo ausente em $GODOT_BIN; execute install-godot-web.sh primeiro"; exit 1; }
[[ -f "$SOURCE_DIR/apps/headless-renderer/headless_renderer.py" ]] || { echo 'headless_renderer.py ausente'; exit 1; }
[[ -f "$SOURCE_DIR/apps/renderer-godot/project.godot" ]] || { echo 'projeto Godot ausente'; exit 1; }

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  xvfb ffmpeg libx11-6 libxext6 libxrender1 libxi6 libxrandr2 libxcursor1 libxinerama1 libgl1

mkdir -p "$RENDERER_DIR" "$INSTALL_DIR/apps/renderer-godot"
rsync -a --delete "$SOURCE_DIR/apps/headless-renderer/" "$RENDERER_DIR/"
rsync -a --delete "$SOURCE_DIR/apps/renderer-godot/" "$INSTALL_DIR/apps/renderer-godot/"
chown -R liveinfinita:liveinfinita "$RENDERER_DIR" "$INSTALL_DIR/apps/renderer-godot"
install -m 0644 "$SOURCE_DIR/deploy/live-infinita-renderer.service" "$UNIT"

systemctl daemon-reload
systemctl enable --now live-infinita-renderer.service
systemctl restart live-infinita-renderer.service

for i in $(seq 1 20); do
  if systemctl is-active --quiet live-infinita-renderer.service; then
    sleep .5
    if systemctl is-active --quiet live-infinita-renderer.service; then
      echo 'Native Renderer ativo.'
      exit 0
    fi
  fi
  sleep .5
done

systemctl status live-infinita-renderer.service --no-pager || true
journalctl -u live-infinita-renderer.service -n 80 --no-pager || true
exit 1
