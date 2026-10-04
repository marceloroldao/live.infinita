#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
echo "008CL_START"
# Existing bridge rollout provides backup, installed-account checks and rollback.
bash "$REPO/deploy/apply-navigation-memory-bridge-008ce-root.sh"
SERVICE=live-infinita-nov-navigation-memory-sync.service
[ "$(systemctl show "$SERVICE" -p Result --value)" = success ]
[ "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" = 0 ]
python3 - <<'PY'
import json,time
from pathlib import Path
cache=json.loads(Path("/var/www/live-infinita-godot/navigation-memory/recall.json").read_text())
assert cache["source"] == "memoria.ia-local-structural-api"
assert cache["world_write_authority"] is False
assert -30 <= time.time()-cache["generated_at_unix"] <= 180
print("008CL_RECALL_FRESH entries=",len(cache["entries"]))
PY
echo "008CL_OK source=$(git -C "$REPO" rev-parse --short HEAD)"
