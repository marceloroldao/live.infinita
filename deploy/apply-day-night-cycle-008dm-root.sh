#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
SERVICE=live-infinita-renderer.service
cd "$REPO"
LOG=/home/etbra/008dm-renderer-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DM_START source=$SHA"
if [ -n "$(git status --porcelain)" ]; then
  echo "008DM_ABORT: existem alterações locais; instalação não iniciada." >&2
  git status --short
  exit 3
fi
BACKUP="/opt/live.infinita/.rollouts/008dm-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(world_map_day_cycle.gd nov_ground_consolidation.gd nov_stuck_recovery.gd world_map_cognitive_terrain.gd nov_navigation_journey.gd world_map_preview.gd world_map_hud.gd world_map_live_feed.gd live_program_overlay.gd live_program_audio.gd world_map_local_motion.gd world_map_traversability.gd world_map_features.gd nov_navigation_experience.gd nature_batch_collision.gd world_map_perceptual_assets.gd world_map_perceptual_vegetation.gd nov_camera_stabilizer.gd nov_navigation_recall.gd nov_navigation_episodes.gd nov_navigation_working_memory.gd nature_local_residency.gd nov_route_goal.gd nov_observed_route.gd)
for f in main_spatial.py world_sky_clock.py; do
  if [ -f "/opt/live.infinita/apps/world-runtime/$f" ]; then cp -a "/opt/live.infinita/apps/world-runtime/$f" "$BACKUP/$f"; fi
done
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
for unit in live-infinita-nov-panel.service live-infinita-nov-panel.timer; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; fi
done
if [ -f /opt/live.infinita/apps/world-runtime/nov_navigation_panel_export.py ]; then
  cp -a /opt/live.infinita/apps/world-runtime/nov_navigation_panel_export.py "$BACKUP/nov_navigation_panel_export.py"
fi
if systemctl is-enabled --quiet live-infinita-nov-panel.timer; then touch "$BACKUP/panel-enabled"; fi
if [ -f /var/www/live-infinita-godot/navigation-memory/status.json ]; then cp -a /var/www/live-infinita-godot/navigation-memory/status.json "$BACKUP/panel-status.json"; fi
cp -a /opt/live.infinita/apps/world-runtime/nov_navigation_recall_export.py "$BACKUP/nov_navigation_recall_export.py"
cp -a /opt/live.infinita/apps/world-runtime/nov_navigation_memory_sync.py "$BACKUP/nov_navigation_memory_sync.py"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
test -d "$WEB"
cp -a "$WEB" "$BACKUP/world-map-preview"
rollback() {
  rc=$?
  trap - ERR
  echo "ROLLBACK 008DM rc=$rc" >&2
  systemctl stop live-infinita-nov-panel.timer live-infinita-nov-panel.service || true
  systemctl stop live-infinita-nov-navigation-memory-sync.timer live-infinita-nov-navigation-memory-sync.service || true
  systemctl disable live-infinita-nov-panel.timer || true
  for unit in live-infinita-nov-panel.service live-infinita-nov-panel.timer; do
    if [ -f "$BACKUP/$unit" ]; then cp -a "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  if [ -f "$BACKUP/nov_navigation_panel_export.py" ]; then
    cp -a "$BACKUP/nov_navigation_panel_export.py" /opt/live.infinita/apps/world-runtime/nov_navigation_panel_export.py
  else
    rm -f /opt/live.infinita/apps/world-runtime/nov_navigation_panel_export.py
  fi
  if [ -f "$BACKUP/panel-status.json" ]; then cp -a "$BACKUP/panel-status.json" /var/www/live-infinita-godot/navigation-memory/status.json; else rm -f /var/www/live-infinita-godot/navigation-memory/status.json; fi
  systemctl daemon-reload || true
  if [ -f "$BACKUP/panel-enabled" ]; then systemctl enable --now live-infinita-nov-panel.timer || true; fi
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then
      install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"
    elif [ "$f" = world_map_day_cycle.gd ] || [ "$f" = nov_ground_consolidation.gd ] || [ "$f" = nov_stuck_recovery.gd ] || [ "$f" = nov_navigation_journey.gd ] || [ "$f" = live_program_overlay.gd ] || [ "$f" = live_program_audio.gd ] || [ "$f" = nov_navigation_experience.gd ] || [ "$f" = nature_batch_collision.gd ] || [ "$f" = nov_camera_stabilizer.gd ] || [ "$f" = nov_navigation_recall.gd ] || [ "$f" = nov_navigation_episodes.gd ] || [ "$f" = nov_navigation_working_memory.gd ] || [ "$f" = nature_local_residency.gd ] || [ "$f" = nov_route_goal.gd ] || [ "$f" = nov_observed_route.gd ]; then
      rm -f "$DST/$f"
    fi
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/nov_navigation_recall_export.py" /opt/live.infinita/apps/world-runtime/nov_navigation_recall_export.py
  install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/nov_navigation_memory_sync.py" /opt/live.infinita/apps/world-runtime/nov_navigation_memory_sync.py
  systemctl start live-infinita-nov-navigation-memory-sync.timer || true
  for f in main_spatial.py world_sky_clock.py; do
    if [ -f "$BACKUP/$f" ]; then cp -a "$BACKUP/$f" "/opt/live.infinita/apps/world-runtime/$f"; else rm -f "/opt/live.infinita/apps/world-runtime/$f"; fi
  done
  systemctl restart live-infinita.service || true
  systemctl restart "$SERVICE" || true
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
systemctl stop live-infinita-nov-navigation-memory-sync.timer live-infinita-nov-navigation-memory-sync.service
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_navigation_memory_sync.py" /opt/live.infinita/apps/world-runtime/nov_navigation_memory_sync.py
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_navigation_recall_export.py" /opt/live.infinita/apps/world-runtime/nov_navigation_recall_export.py.new-008dm
mv /opt/live.infinita/apps/world-runtime/nov_navigation_recall_export.py.new-008dm /opt/live.infinita/apps/world-runtime/nov_navigation_recall_export.py
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_navigation_panel_export.py" /opt/live.infinita/apps/world-runtime/nov_navigation_panel_export.py
for unit in live-infinita-nov-panel.service live-infinita-nov-panel.timer; do
  install -o root -g root -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now live-infinita-nov-panel.timer
systemctl start live-infinita-nov-navigation-memory-sync.timer
for f in main_spatial.py world_sky_clock.py; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/$f" "/opt/live.infinita/apps/world-runtime/$f.new-008dm"
  mv "/opt/live.infinita/apps/world-runtime/$f.new-008dm" "/opt/live.infinita/apps/world-runtime/$f"
done
systemctl restart live-infinita.service
systemctl is-active --quiet live-infinita.service
systemctl restart "$SERVICE"
sleep 10
systemctl start live-infinita-nov-panel.service
systemctl is-active --quiet live-infinita-nov-panel.timer
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
assert b["nature_collision_cpu_transforms"] is True
assert b["nature_solid_layer_collision"] is True
assert b["camera_stabilization"] is True
assert b["camera_collision_release_delay_seconds"] == 0.6
assert b["camera_collision_release_mps"] == 2
assert b["navigation_live_trial_error"] is True
assert b["navigation_live_route_search"] is False
assert b["navigation_complete_journey_quality"] is True
assert b["navigation_learning_panel"] is True
assert b["navigation_one_quality_sample_per_journey"] is True
assert b["navigation_panel_current_distance"] is True
assert b["navigation_cognitive_water_egress"] is True
assert b["navigation_blocked_status_heartbeat"] is True
assert b["navigation_absolute_web_requests"] is True
assert b["navigation_independent_panel_refresh"] is True
assert b["navigation_server_recall_metrics"] is True
assert b["navigation_stuck_recovery"] is True
assert b["day_night_cycle"] is True
assert b["day_night_clock_source"]=="persisted_simulation_clock"
assert b["day_night_cycle_logical_minutes"]==60
assert b["memory_linked_celestial_bodies"] is False
assert b["ground_new_sample_blending"] is True
assert b["ground_new_sample_grade_limit"]==0.65
assert b["ground_smooth_highland_transition"] is True
assert b["navigation_confined_recovery_seconds"]==30
assert b["navigation_no_progress_recovery_seconds"]==90
with urllib.request.urlopen("https://live.etbra.com.br/godot/navigation-memory/status.json",timeout=15) as r:
    panel=json.load(r)
assert panel["schema"]=="live-infinita-nov-panel/v1"
assert panel["source"]=="native_renderer_journey"
assert b["navigation_anticipation"] is True
assert b["navigation_visible_goal_priority"] is True
assert b["navigation_observed_routes"] is True
assert b["navigation_frontier_exploration"] is True
assert b["navigation_observed_shortcuts"] is True
assert b["navigation_verified_goal_connection"] is True
assert b["navigation_changed_passage_replanning"] is True
assert b["navigation_ram_candidate_revalidation"] is True
assert b["navigation_destination_body_clearance"] is True
assert b["navigation_shortcut_range_m"] == 6
assert b["navigation_shortcut_max_probes"] == 3
assert b["navigation_coverage_cell_m"] == 8
assert b["navigation_goal_hard_limit_seconds"] == 900
assert b["navigation_step_perception_consistency"] is True
assert b["navigation_walkable_destinations"] is True
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
print("008DM_PUBLIC_OK",b["source_commit"])
PY
trap - ERR
echo "008DM_OK source=$SHA backup=$BACKUP"
