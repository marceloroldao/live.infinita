#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
echo "008CJ_START"
# The bridge installer backs up modules and restores them on failed verification.
# Renderer and Memoria services remain running; only the bridge is updated.
bash "$REPO/deploy/apply-navigation-memory-bridge-008ce-root.sh"
SERVICE=live-infinita-nov-navigation-memory-sync.service
[ "$(systemctl show "$SERVICE" -p Result --value)" = success ]
[ "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" = 0 ]
echo "008CJ_OK source=$(git -C "$REPO" rev-parse --short HEAD)"
