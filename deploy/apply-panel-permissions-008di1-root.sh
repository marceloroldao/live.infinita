#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/world-runtime
UNIT=live-infinita-nov-panel.service
TIMER=live-infinita-nov-panel.timer
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo "008DI1_ABORT alterações locais"; exit 3; }
LOG=/home/etbra/008di1-panel-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
exec > >(tee -a "$LOG") 2>&1
BACKUP="/opt/live.infinita/.rollouts/008di1-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "$DST/nov_navigation_panel_export.py" "$BACKUP/"
cp -a "/etc/systemd/system/$UNIT" "$BACKUP/"
rollback() {
  rc=$?
  trap - ERR
  systemctl stop "$TIMER" "$UNIT" || true
  cp -a "$BACKUP/nov_navigation_panel_export.py" "$DST/"
  cp -a "$BACKUP/$UNIT" "/etc/systemd/system/$UNIT"
  systemctl daemon-reload || true
  systemctl start "$TIMER" || true
  echo "008DI1_ROLLBACK rc=$rc"
  exit "$rc"
}
trap rollback ERR
systemctl stop "$TIMER" "$UNIT"
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_navigation_panel_export.py" "$DST/nov_navigation_panel_export.py"
install -o root -g root -m 0644 "$REPO/deploy/$UNIT" "/etc/systemd/system/$UNIT"
systemctl daemon-reload
systemctl start "$UNIT"
systemctl start "$TIMER"
python3 - <<'CHECK'
import json,time,urllib.request
from pathlib import Path
p=Path("/var/www/live-infinita-godot/navigation-memory/status.json")
assert p.stat().st_mode & 0o777 == 0o644
with urllib.request.urlopen("https://live.etbra.com.br/godot/navigation-memory/status.json?check="+str(int(time.time())),timeout=15) as response:
    data=json.load(response)
assert data["schema"]=="live-infinita-nov-panel/v1"
assert time.time()-data["generated_at_unix"]<60
print("008DI1_PUBLIC_OK")
CHECK
trap - ERR
echo "008DI1_OK source=$(git rev-parse --short HEAD) backup=$BACKUP"
