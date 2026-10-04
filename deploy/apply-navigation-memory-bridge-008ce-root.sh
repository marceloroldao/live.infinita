#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/world-runtime
SERVICE=live-infinita-nov-navigation-memory-sync.service
TIMER=live-infinita-nov-navigation-memory-sync.timer
SCRIPT=nov_navigation_memory_sync.py
CHECKPOINT=/var/lib/live-infinita/memoria-local/nov-navigation-ingest.checkpoint.json
cd "$REPO"
LOG=/home/etbra/008ce-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008CE_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo "008CE_ABORT alterações locais"; exit 3; }
test -s "$DST/nov_spatial_memory_sync.py"
test -s /etc/live-infinita/memoria-local.env
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-renderer.service
PYTHONPATH="$REPO:$REPO/apps/world-runtime" PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "$REPO/tests" -p test_nov_navigation_memory_sync.py
BACKUP="/opt/live.infinita/.rollouts/008ce-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
if [ -f "$DST/$SCRIPT" ]; then cp -a "$DST/$SCRIPT" "$BACKUP/$SCRIPT"; fi
for unit in "$SERVICE" "$TIMER"; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; fi
done
WAS_ENABLED=0
WAS_ACTIVE=0
if systemctl is-enabled --quiet "$TIMER"; then WAS_ENABLED=1; fi
if systemctl is-active --quiet "$TIMER"; then WAS_ACTIVE=1; fi
rollback() {
  rc=$?
  trap - ERR
  echo "008CE_ROLLBACK rc=$rc" >&2
  systemctl disable --now "$TIMER" || true
  systemctl stop "$SERVICE" || true
  if [ -f "$BACKUP/$SCRIPT" ]; then cp -a "$BACKUP/$SCRIPT" "$DST/$SCRIPT"; else rm -f "$DST/$SCRIPT"; fi
  for unit in "$SERVICE" "$TIMER"; do
    if [ -f "$BACKUP/$unit" ]; then cp -a "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  systemctl daemon-reload || true
  if [ "$WAS_ENABLED" -eq 1 ]; then systemctl enable "$TIMER" || true; fi
  if [ "$WAS_ACTIVE" -eq 1 ]; then systemctl start "$TIMER" || true; fi
  # Durable acknowledgements already committed remain idempotent on retries.
  exit "$rc"
}
trap rollback ERR
if [ -f "/etc/systemd/system/$TIMER" ]; then systemctl stop "$TIMER"; fi
if [ -f "/etc/systemd/system/$SERVICE" ]; then systemctl stop "$SERVICE"; fi
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/$SCRIPT" "$DST/$SCRIPT"
# Service account cannot traverse the private /home/etbra directory.
# Validate the installed script under the same readable /opt paths as systemd.
sudo -u liveinfinita env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="/opt/live.infinita:$DST" /opt/live.infinita/.venv/bin/python "$DST/$SCRIPT" --preview
for unit in "$SERVICE" "$TIMER"; do
  install -o root -g root -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl reset-failed "$SERVICE" || true
systemctl start "$SERVICE"
[ "$(systemctl show "$SERVICE" -p Result --value)" = success ]
[ "$(systemctl show "$SERVICE" -p ExecMainStatus --value)" = 0 ]
python3 - "$CHECKPOINT" <<'VERIFY_ACK'
import json,sys
from pathlib import Path
state=json.loads(Path(sys.argv[1]).read_text())
assert state["schema"] == "live-infinita-nov-navigation-checkpoint/v1"
assert state["confirmed"] > 0
assert state["last_observation_id"].startswith("structural-event:")
print("008CE_DURABLE_ACK_OK confirmed=",state["confirmed"],"observation_id=",state["last_observation_id"])
VERIFY_ACK
systemctl enable --now "$TIMER"
systemctl is-active --quiet "$TIMER"
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-memoria-local.service
journalctl -u "$SERVICE" -n 8 --no-pager
trap - ERR
echo "008CE_OK source=$SHA backup=$BACKUP"
