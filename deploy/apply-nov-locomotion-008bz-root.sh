#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
SERVICE=live-infinita-renderer.service
cd "$REPO"
test -z "$(git status --porcelain)"
SHA="$(git rev-parse --short HEAD)"
LOG=/home/etbra/008bz-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "008BZ_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008bz-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_character_visual.gd world_map_preview.gd)
for f in "${FILES[@]}"; do cp -a "$DST/$f" "$BACKUP/$f"; done
test -d "$WEB"
cp -a "$WEB" "$BACKUP/world-map-preview"
rollback() {
  rc=$?
  trap - ERR
  echo "ROLLBACK 008BZ rc=$rc" >&2
  for f in "${FILES[@]}"; do
    install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  systemctl restart "$SERVICE" || true
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
systemctl restart "$SERVICE"
sleep 10
systemctl is-active --quiet "$SERVICE"
python3 - "$SHA" <<'PY'
import json,sys,urllib.request
with urllib.request.urlopen("https://live.etbra.com.br/godot/world-map-preview/build.json",timeout=20) as r:
    b=json.load(r)
assert b["source_commit"] == sys.argv[1]
assert b["nov_smooth_locomotion"] is True
assert b["nov_procedural_gait"] is True
with urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=10) as r:
    assert json.load(r)["ok"] is True
print("008BZ_PUBLIC_OK",b["source_commit"])
PY
trap - ERR
echo "008BZ_OK source=$SHA backup=$BACKUP"
