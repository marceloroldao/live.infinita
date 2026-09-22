#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

chmod +x deploy/server-cognitive-rc1/*.sh deploy/update.sh

echo "[1/3] Bootstrapping pinned dependencies..."
./deploy/server-cognitive-rc1/bootstrap.sh

echo "[2/3] Running HTTP + checkpoint restart smoke..."
./deploy/server-cognitive-rc1/smoke.sh

echo "[3/3] Installing user systemd service..."
./deploy/server-cognitive-rc1/install-service.sh

echo
echo "Server Cognitive RC1 installed."
echo "Dashboard (via SSH tunnel): http://127.0.0.1:8090/"
echo "Watch: ./deploy/server-cognitive-rc1/watch.sh"
echo "Logs:  journalctl --user -u live-infinita-cognitive.service -f"
