#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
SERVICE=live-infinita-renderer.service
cd "$REPO"
LOG=/home/etbra/008dr-perception-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DR_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo '008DR_ABORT: checkout precisa estar limpo'; exit 3; }
[ -f "$DST/world_map_weather.gd" ]
[ -d "$WEB" ]
BACKUP="/opt/live.infinita/.rollouts/008dr-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_visual_perception.gd world_map_preview.gd)
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?
  trap - ERR
  echo "008DR_ROLLBACK rc=$rc"
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl restart "$SERVICE" || true
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
systemctl restart "$SERVICE"
sleep 5
systemctl is-active --quiet "$SERVICE"
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'PY'
import json,sys,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json',timeout=20) as response:b=json.load(response)
assert b['source_commit']==sys.argv[1]
assert b['nov_visual_perception'] is True
assert b['nov_sight_day_range_m']==24 and b['nov_sight_night_range_m']==12
assert b['nov_sight_horizontal_fov_deg']==120 and b['nov_sight_obstacle_occlusion'] is True
assert b['navigation_live_trial_error'] is True
assert b['live_physical_collision'] is True
assert b['camera_stabilization'] is True
assert b['physical_weather'] is True and b['weather_inference_influence'] is False
print('008DR_PUBLIC_PERCEPTION_OK',b['source_commit'])
PY
echo "008DR_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Sensor preparado; animais entram na próxima etapa.'
