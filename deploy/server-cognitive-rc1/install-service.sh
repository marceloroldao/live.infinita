#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE="$ROOT/deploy/server-cognitive-rc1/live-infinita-cognitive.service"
TARGET_DIR="$HOME/.config/systemd/user"
TARGET="$TARGET_DIR/live-infinita-cognitive.service"

mkdir -p "$TARGET_DIR"
cp "$SOURCE" "$TARGET"
chmod 0644 "$TARGET"

systemctl --user daemon-reload
systemctl --user enable --now live-infinita-cognitive.service

echo "Installed: $TARGET"
systemctl --user --no-pager status live-infinita-cognitive.service || true
