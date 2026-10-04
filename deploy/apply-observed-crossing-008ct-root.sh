#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
SERVICE=live-infinita-renderer.service
cd "$REPO"
LOG=/home/etbra/008ct-renderer-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008CT_START source=$SHA"
if [ -n "$(git status --porcelain)" ]; then
  echo "008CT_ABORT: existem alterações locais; instalação não iniciada." >&2
  git status --short
  exit 3
fi
BACKUP="/opt/live.infinita/.rollouts/008ct-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(world_map_preview.gd world_map_hud.gd world_map_live_feed.gd live_program_overlay.gd live_program_audio.gd world_map_local_motion.gd world_map_traversability.gd world_map_features.gd nov_navigation_experience.gd nature_batch_collision.gd world_map_perceptual_assets.gd world_map_perceptual_vegetation.gd nov_camera_stabilizer.gd nov_navigation_recall.gd nov_navigation_episodes.gd nov_navigation_working_memory.gd nature_local_residency.gd nov_route_goal.gd nov_observed_route.gd)
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
test -d "$WEB"
cp -a "$WEB" "$BACKUP/world-map-preview"
rollback() {
  rc=$?
  trap - ERR
  echo "ROLLBACK 008CT rc=$rc" >&2
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then
      install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"
    elif [ "$f" = live_program_overlay.gd ] || [ "$f" = live_program_audio.gd ] || [ "$f" = nov_navigation_experience.gd ] || [ "$f" = nature_batch_collision.gd ] || [ "$f" = nov_camera_stabilizer.gd ] || [ "$f" = nov_navigation_recall.gd ] || [ "$f" = nov_navigation_episodes.gd ] || [ "$f" = nov_navigation_working_memory.gd ] || [ "$f" = nature_local_residency.gd ] || [ "$f" = nov_route_goal.gd ] || [ "$f" = nov_observed_route.gd ]; then
      rm -f "$DST/$f"
    fi
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
sleep 10
systemctl is-active --quiet "$SERVICE"
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'PY'
import json,sys,urllib.request
with urllib.request.urlopen("https://live.etbra.com.br/godot/world-map-preview/build.json",timeout=20) as r:
    b=json.load(r)
assert b["source_commit"] == sys.argv[1]
assert b["nov_smooth_locomotion"] is True
assert b["nov_procedural_gait"] is True
assert b["audience_overlay"] is True
assert b["live_infinita_brand"] is True
assert b["live_infinita_brand_position"] == "top"
assert b["narrator_caption"] is True
assert b["program_audio"] is True
assert b["live_exploration_controls"] is False
assert b["ground_surface_alignment"] is True
assert b["live_physical_collision"] is True
assert b["camera_stabilization"] is True
assert b["navigation_anticipation"] is True
assert b["navigation_visible_goal_priority"] is True
assert b["navigation_observed_routes"] is True
assert b["navigation_observed_window_side_m"] == 64
assert b["navigation_goal_visibility_range_m"] == 3
assert b["navigation_memoria_recall"] is True
assert b["navigation_chronological_episodes"] is True
assert b["navigation_working_memory"] is True
assert b["ground_shared_inference_samples"] is True
assert b["navigation_committed_goal"] is True
assert b["navigation_goal_reassessment_seconds"] == 180
assert b["local_object_residency"] is True
assert b["local_object_protected_radius_m"] == 45
with urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=10) as r:
    assert json.load(r)["ok"] is True
print("008CT_PUBLIC_OK",b["source_commit"])
PY
trap - ERR
echo "008CT_OK source=$SHA backup=$BACKUP"
