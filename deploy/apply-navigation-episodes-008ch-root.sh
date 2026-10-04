#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/world-runtime
SERVICE=live-infinita-nov-navigation-memory-sync.service
TIMER=live-infinita-nov-navigation-memory-sync.timer
PUBLIC=/var/www/live-infinita-godot/navigation-memory
PRIVATE=/var/lib/live-infinita/memoria-local/navigation-recall.json
cd "$REPO"
LOG=/home/etbra/008ch-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "008CH_START source=$(git rev-parse --short HEAD)"
[ -z "$(git status --porcelain)" ] || { echo "008CH_ABORT alterações locais"; exit 3; }
systemctl is-active --quiet "$TIMER"
systemctl is-active --quiet live-infinita-renderer.service
BACKUP="/opt/live.infinita/.rollouts/008ch-bridge-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_navigation_memory_sync.py nov_navigation_recall_export.py nov_navigation_episode_sync.py)
for file in "${FILES[@]}"; do
  if [ -f "$DST/$file" ]; then cp -a "$DST/$file" "$BACKUP/$file"; fi
done
for unit in "$SERVICE" "$TIMER"; do cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; done
if [ -d "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/navigation-public"; fi
if [ -f "$PRIVATE" ]; then cp -a "$PRIVATE" "$BACKUP/navigation-private.json"; fi
rollback() {
  rc=$?
  trap - ERR
  echo "008CH_BRIDGE_ROLLBACK rc=$rc"
  systemctl stop "$TIMER" "$SERVICE" || true
  for file in "${FILES[@]}"; do
    if [ -f "$BACKUP/$file" ]; then cp -a "$BACKUP/$file" "$DST/$file"; else rm -f "$DST/$file"; fi
  done
  for unit in "$SERVICE" "$TIMER"; do cp -a "$BACKUP/$unit" "/etc/systemd/system/$unit"; done
  if [ -d "$BACKUP/navigation-public" ]; then rsync -a --delete "$BACKUP/navigation-public/" "$PUBLIC/"; else rm -f "$PUBLIC/recall.json"; fi
  if [ -f "$BACKUP/navigation-private.json" ]; then cp -a "$BACKUP/navigation-private.json" "$PRIVATE"; else rm -f "$PRIVATE"; fi
  systemctl daemon-reload || true
  systemctl enable --now "$TIMER" || true
  exit "$rc"
}
trap rollback ERR
bash "$REPO/deploy/apply-navigation-memory-bridge-008ce-root.sh"
python3 - "$PRIVATE" <<'CHECK_RECALL'
import json,sys,urllib.request
from pathlib import Path
snapshot=json.loads(Path(sys.argv[1]).read_text())
assert snapshot["schema"]=="live-infinita-nov-navigation-recall/v1"
assert snapshot["source"]=="memoria.ia-local-structural-api"
assert len(snapshot["entries"])>0
assert all(row["observation_id"].startswith("structural-event:") for row in snapshot["entries"])
with urllib.request.urlopen("https://live.etbra.com.br/godot/navigation-memory/recall.json",timeout=15) as response:
    public=json.load(response)
assert public["schema"]==snapshot["schema"]
assert public["source"]==snapshot["source"]
assert len(public["entries"])>0
print("008CH_MEMORIA_RETRIEVED entries=",len(snapshot["entries"]),"public_delivery=true")
CHECK_RECALL
bash "$REPO/deploy/apply-navigation-episodes-renderer-008ch-root.sh"
systemctl is-active --quiet "$TIMER"
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-renderer.service
trap - ERR
echo "008CH_OK episodes_enabled=true; aguarde 30s de movimento para a primeira experiência cronológica."
