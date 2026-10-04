#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
# Install backward compatible archive validation before emitting route identities.
bash "$REPO/deploy/apply-navigation-memory-bridge-008ce-root.sh"
bash "$REPO/deploy/apply-stable-route-goal-renderer-008cn-root.sh"
echo "008CN_COMPLETE source=$(git -C "$REPO" rev-parse --short HEAD)"
