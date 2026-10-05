#!/usr/bin/env bash
# Publish the optional Vale de Nov world-map preview below the existing /godot/ location.
# Does not restart services, edit nginx, replace the broadcast export, or write World State.
set -Eeuo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT_DIR="${PROJECT_DIR:-$SOURCE_DIR/apps/renderer-godot}"
WEB_ROOT="${WEB_ROOT:-/var/www/live-infinita-godot}"
ENGINE_ROOT="${GODOT_ENGINE_ROOT:-/opt/live-infinita-godot/engine}"
PREVIEW_NAME="world-map-preview"
SMOKE_TEST="$SOURCE_DIR/tests/godot_world_map_traversal_smoke.gd"
SOURCE_SHA="${LIVE_INFINITA_SOURCE_SHA:-$(git -C "$SOURCE_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)}"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/export-world-map-preview-web.sh" >&2
  exit 1
fi

for required in "$PROJECT_DIR/project.godot" "$PROJECT_DIR/export_presets.cfg" "$PROJECT_DIR/world_map_preview.tscn" "$PROJECT_DIR/world_map_preview.gd" "$PROJECT_DIR/world_map_live_feed.gd" "$PROJECT_DIR/world_map_live_visual.gd" "$PROJECT_DIR/world_map_cognitive_terrain.gd" "$PROJECT_DIR/world_map_hud.gd" "$PROJECT_DIR/world_map_local_motion.gd" "$PROJECT_DIR/world_map_traversability.gd" "$PROJECT_DIR/world_map_layout.gd" "$PROJECT_DIR/world_map_features.gd" "$PROJECT_DIR/world_map_001.json" "$PROJECT_DIR/nature_asset_catalog.gd" "$SMOKE_TEST"; do
  if [[ ! -f "$required" ]]; then
    echo "Arquivo Godot ausente: $required" >&2
    exit 2
  fi
done

# This directory must already be served by the existing nginx /godot/ alias.
# Do not silently create a separate non-public directory or modify production.
if [[ ! -s "$WEB_ROOT/index.html" ]]; then
  echo "Export principal ausente em $WEB_ROOT; configure /godot/ antes de instalar a prévia." >&2
  exit 3
fi
if ! command -v rsync >/dev/null 2>&1; then
  echo "Instale rsync primeiro (sudo apt-get install rsync)." >&2
  exit 4
fi

GODOT_BIN="$(find "$ENGINE_ROOT" -maxdepth 1 -type f -name 'Godot_v*_linux.x86_64' -perm -u+x 2>/dev/null | sort | tail -n1 || true)"
if [[ -z "$GODOT_BIN" ]]; then
  echo "Engine Godot Web não instalada em $ENGINE_ROOT." >&2
  echo "Primeira instalação: sudo bash deploy/install-godot-web.sh" >&2
  exit 5
fi

TEMP_ROOT="$(mktemp -d /tmp/live-infinita-world-map-web.XXXXXX)"
STAGE=""
BACKUP=""
cleanup() {
  [[ -z "$STAGE" || ! -d "$STAGE" ]] || rm -rf -- "$STAGE"
  rm -rf -- "$TEMP_ROOT"
}
trap cleanup EXIT

WORK_PROJECT="$TEMP_ROOT/renderer-godot"
BUILD_DIR="$TEMP_ROOT/export"
mkdir -p "$WORK_PROJECT" "$BUILD_DIR"

# Never change source project.godot (main.tscn stays the broadcast scene).
rsync -a --exclude '/.godot/' --exclude 'build/' "$PROJECT_DIR/" "$WORK_PROJECT/"
python3 - "$WORK_PROJECT/project.godot" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
raw = path.read_text(encoding="utf-8")
production = 'run/main_scene="res://main.tscn"'
preview = 'run/main_scene="res://world_map_preview.tscn"'
if raw.count(production) != 1:
    raise SystemExit("Cena principal inesperada; prévia não publicada.")
path.write_text(raw.replace(production, preview, 1), encoding="utf-8")
PY

# Import glTF into the isolated project before exporting the scene.
IMPORT_LOG="$TEMP_ROOT/import.log"
SMOKE_LOG="$TEMP_ROOT/traversability-smoke.log"
EXPORT_LOG="$TEMP_ROOT/export.log"
echo "[world-map-preview] Importando recursos em cópia isolada."
set +e
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT_BIN" --headless --editor --quit --path "$WORK_PROJECT" >"$IMPORT_LOG" 2>&1
IMPORT_STATUS=$?
set -e
if ((IMPORT_STATUS != 0)) || grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$IMPORT_LOG"; then
  cat "$IMPORT_LOG" >&2
  echo "Falha no import Godot; transmissão atual preservada." >&2
  exit 6
fi

echo "[world-map-preview] Validando travessabilidade física e modo local."
set +e
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT_BIN" --headless --audio-driver Dummy --path "$WORK_PROJECT" --script "$SMOKE_TEST" -- --offline-tour >"$SMOKE_LOG" 2>&1
SMOKE_STATUS=$?
set -e
if ((SMOKE_STATUS != 0)) || grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$SMOKE_LOG"; then
  cat "$SMOKE_LOG" >&2
  echo "Falha no smoke de travessabilidade; prévia anterior preservada." >&2
  exit 7
fi
grep -q 'World-map traversal smoke: 0 failures' "$SMOKE_LOG" || {
  cat "$SMOKE_LOG" >&2
  echo "Smoke não confirmou zero falhas; prévia anterior preservada." >&2
  exit 7
}

echo "[world-map-preview] Validando caminhada e câmera de NOV."
for extra_smoke in godot_nov_locomotion_008bz_smoke.gd godot_nov_grounded_presentation_smoke.gd godot_live_program_008cb_smoke.gd godot_ground_surface_008cc_smoke.gd godot_navigation_experience_008cd_smoke.gd godot_camera_stabilization_008cf_smoke.gd godot_navigation_anticipation_008cg_smoke.gd godot_navigation_episodes_008ch_smoke.gd godot_navigation_working_memory_008ci_smoke.gd godot_nature_residency_008ck_smoke.gd godot_route_goal_008cn_smoke.gd godot_ground_continuity_008co_smoke.gd godot_navigation_goal_quality_008cs_smoke.gd godot_observed_crossing_008ct_smoke.gd godot_navigation_consistency_008cu_smoke.gd godot_nature_collision_008cv_smoke.gd godot_camera_contact_008cw_smoke.gd godot_frontier_routes_008cx_smoke.gd godot_route_shortcuts_008cy_smoke.gd godot_goal_approach_008da_smoke.gd godot_changing_routes_008db_smoke.gd godot_live_learning_008df_smoke.gd godot_journey_samples_008dg_smoke.gd godot_water_egress_008dh_smoke.gd godot_panel_delivery_008di_smoke.gd godot_stuck_recovery_008dk_smoke.gd; do
  EXTRA_LOG="$TEMP_ROOT/$extra_smoke.log"
  if ! GODOT_SILENCE_ROOT_WARNING=1 timeout 60s "$GODOT_BIN" --headless --audio-driver Dummy --path "$WORK_PROJECT" --script "$SOURCE_DIR/tests/$extra_smoke" -- --offline-tour >"$EXTRA_LOG" 2>&1; then
    cat "$EXTRA_LOG" >&2
    exit 7
  fi
  if grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$EXTRA_LOG"; then
    cat "$EXTRA_LOG" >&2
    exit 7
  fi
done

echo "[world-map-preview] Exportando Web em diretório temporário."
set +e
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT_BIN" --headless --path "$WORK_PROJECT" --export-release "Web" "$BUILD_DIR/index.html" >"$EXPORT_LOG" 2>&1
EXPORT_STATUS=$?
set -e
if ((EXPORT_STATUS != 0)) || grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$EXPORT_LOG"; then
  cat "$EXPORT_LOG" >&2
  echo "Falha no export Godot; transmissão atual preservada." >&2
  exit 8
fi
if [[ ! -s "$BUILD_DIR/index.html" ]] ||
   ! find "$BUILD_DIR" -maxdepth 1 -type f -name '*.wasm' -size +0c -print -quit | grep -q . ||
   ! find "$BUILD_DIR" -maxdepth 1 -type f -name '*.pck' -size +0c -print -quit | grep -q .; then
  echo "Export Web incompleto (index.html / wasm / pck ausente)." >&2
  exit 9
fi

cat >"$BUILD_DIR/build.json" <<EOF
{
  "source_commit": "$SOURCE_SHA",
  "project": "Live Infinita - Vale de Nov world-map preview",
  "scene": "res://world_map_preview.tscn",
  "renderer": "godot-web",
  "map_schema": "live-infinita-visual-world-map/v1",
  "world_size_m": 2048,
  "logical_sectors": 1024,
  "active_sector_cap": 9,
  "traversability": "local-physics-read-only",
  "touch_controls": true,
  "nov_smooth_locomotion": true,
  "nov_procedural_gait": true,
  "audience_overlay": true,
  "live_infinita_brand": true,
  "live_infinita_brand_position": "top",
  "narrator_caption": true,
  "narrator_caption_position": "center",
  "program_audio": true,
  "live_exploration_controls": false,
  "ground_surface_alignment": true,
  "live_physical_collision": true,
  "nature_collision_cpu_transforms": true,
  "nature_solid_layer_collision": true,
  "camera_stabilization": true,
  "camera_collision_release_delay_seconds": 0.6,
  "camera_collision_release_mps": 2,
  "navigation_live_trial_error": true,
  "navigation_live_route_search": false,
  "navigation_complete_journey_quality": true,
  "navigation_learning_panel": true,
  "navigation_one_quality_sample_per_journey": true,
  "navigation_panel_current_distance": true,
  "navigation_cognitive_water_egress": true,
  "navigation_blocked_status_heartbeat": true,
  "navigation_absolute_web_requests": true,
  "navigation_independent_panel_refresh": true,
  "navigation_server_recall_metrics": true,
  "navigation_stuck_recovery": true,
  "navigation_confined_recovery_seconds": 30,
  "navigation_no_progress_recovery_seconds": 90,
  "navigation_anticipation": true,
  "navigation_visible_goal_priority": true,
  "navigation_observed_routes": true,
  "navigation_frontier_exploration": true,
  "navigation_observed_shortcuts": true,
  "navigation_verified_goal_connection": true,
  "navigation_changed_passage_replanning": true,
  "navigation_ram_candidate_revalidation": true,
  "navigation_destination_body_clearance": true,
  "navigation_shortcut_range_m": 6,
  "navigation_shortcut_max_probes": 3,
  "navigation_coverage_cell_m": 8,
  "navigation_goal_hard_limit_seconds": 900,
  "navigation_step_perception_consistency": true,
  "navigation_walkable_destinations": true,
  "navigation_observed_window_side_m": 64,
  "navigation_goal_visibility_range_m": 3,
  "navigation_memoria_recall": true,
  "navigation_experience": "renderer-local",
  "navigation_chronological_episodes": true,
  "navigation_working_memory": true,
  "ground_shared_inference_samples": true,
  "ground_consolidation_lifetime": "renderer-session",
  "navigation_committed_goal": true,
  "navigation_goal_reassessment_seconds": 180,
  "navigation_promotion_successful_reuses": 3,
  "local_object_residency": true,
  "local_object_protected_radius_m": 45,
  "cognitive_visual_inertia": true,
  "visual_refresh_hint_seconds": 120,
  "ecological_continuous_transitions": true,
  "ecological_affinities": [
    "forest",
    "meadow",
    "shrub",
    "wetland",
    "alpine"
  ]
}
EOF

# Atomic replacement of preview subfolder only. Existing /godot/index.* untouched.
STAGE="$(mktemp -d "$WEB_ROOT/.world-map-preview.stage.XXXXXX")"
rsync -a "$BUILD_DIR/" "$STAGE/"
chown -R www-data:www-data "$STAGE"
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +

TARGET="$WEB_ROOT/$PREVIEW_NAME"
if [[ -e "$TARGET" && ! -d "$TARGET" ]]; then
  echo "Destino ocupado por arquivo: $TARGET" >&2
  exit 10
fi
if [[ -d "$TARGET" ]]; then
  BACKUP="$WEB_ROOT/.world-map-preview.previous.$$"
  mv -- "$TARGET" "$BACKUP"
fi
if ! mv -- "$STAGE" "$TARGET"; then
  if [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
    mv -- "$BACKUP" "$TARGET"
  fi
  echo "Falha ao publicar; prévia anterior restaurada." >&2
  exit 11
fi
STAGE=""
[[ -z "$BACKUP" ]] || rm -rf -- "$BACKUP"

echo "[world-map-preview] Publicação concluída: $TARGET"
echo "[world-map-preview] Abra https://live.etbra.com.br/godot/world-map-preview/"
echo "[world-map-preview] A live 2D /godot/, /nov-preview/ e o mundo persistente não foram alterados."
