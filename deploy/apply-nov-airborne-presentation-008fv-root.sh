#!/usr/bin/env bash
# User-run rollout. Preserve history and install physical support presentation.
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
ROOT=/var/www/live-infinita-godot
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008FV_ABORT checkout precisa estar limpo'; exit 3; }
for u in live-infinita-renderer.service live-infinita-memoria-local.service live-infinita-animal-approach.timer live-infinita-animal-context.timer live-infinita-animal-search.timer; do systemctl is-active --quiet "$u"; done
# Require unchanged perception/context dependencies from the already applied 008FG.
for f in nov_animal_approach.gd nov_animal_approach_history.gd nov_animal_context_history.gd nov_animal_search_intent.gd nov_animal_contact_search.gd nov_ground_response.gd nov_locomotion_response.gd nov_terrain_response.gd nov_navigation_journey.gd world_map_local_motion.gd world_map_traversability.gd; do cmp "apps/renderer-godot/$f" "$DST/$f"; done
LOG=/home/etbra/008fv-nov-airborne-presentation-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008FV_START source=$SHA airborne_presentation=true"
BACKUP="/opt/live.infinita/.rollouts/008fv-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_character_visual.gd world_map_preview.gd)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a "$ROOT/index.html" "$BACKUP/live-index.html"
cp -a "$ROOT/build.json" "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008FV_ROLLBACK rc=$rc"
  systemctl stop live-infinita-renderer.service || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" "$ROOT/index.html"
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" "$ROOT/build.json"
  systemctl daemon-reload || true
  systemctl restart live-infinita-renderer.service || true
  echo 'Memórias, animais e diário privado preservados; versão anterior restaurada.'
  exit "$rc"
}
trap rollback ERR
# Native authority stays disabled during export; physical tests enable their isolated fixtures explicitly.
LIVE_INFINITA_NAVIGATION_COST_SHIFT=1 LIVE_INFINITA_NAVIGATION_CONTACT_TURNS=1 LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION=1 LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE=1 LIVE_INFINITA_ANIMAL_APPROACH_ENABLED=1 LIVE_INFINITA_ANIMAL_CONTEXT_ENABLED=1 LIVE_INFINITA_ANIMAL_CONTACT_SEARCH_ENABLED=1 LIVE_INFINITA_NOV_INERTIAL_MOTION=1 LIVE_INFINITA_NOV_GRAVITY=1 LIVE_INFINITA_NOV_TERRAIN_RESPONSE=1 LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
systemctl stop live-infinita-renderer.service
for f in "${FILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"; cmp "$REPO/apps/renderer-godot/$f" "$DST/$f"; done
systemctl daemon-reload
RESTART_AT="$(python3 -c 'import time; print(time.time())')"
systemctl restart live-infinita-renderer.service
python3 - "$RESTART_AT" <<'NATIVE_CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
for _ in range(60):
    try:
        d=json.loads(p.read_text())
        assert d['generated_at_unix']>=float(sys.argv[1]) and -5<time.time()-d['generated_at_unix']<10
        assert d.get('last_error') is None and d['approach']['history']['storage_ready'] and d['contact_search']['enabled']
        print('008FV_NATIVE_HEALTH_OK');break
    except (OSError,ValueError,KeyError,TypeError,AssertionError):time.sleep(1)
else:raise RuntimeError('Renderer não publicou estado recente e saudável')
NATIVE_CHECK
PID="$(systemctl show live-infinita-renderer.service -p MainPID --value)"
for flag in LIVE_INFINITA_NOV_GRAVITY LIVE_INFINITA_NOV_INERTIAL_MOTION LIVE_INFINITA_NOV_TERRAIN_RESPONSE; do grep -zq "$flag=1" "/proc/$PID/environ"; done
echo "008FV_NATIVE_FLAG_OK pid=$PID"
for u in live-infinita-renderer.service live-infinita-memoria-local.service live-infinita-animal-approach.timer live-infinita-animal-context.timer live-infinita-animal-search.timer; do systemctl is-active --quiet "$u"; done
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'PUBLIC_CHECK'
import urllib.request,json,time,sys
d=json.load(urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20))
assert d['source_commit']==sys.argv[1] and d['nov_inertial_motion'] is True and d['nov_gravity'] is True and d['nov_brake_before_sharp_turn'] is True and d['nov_terrain_response'] is True and d['nov_airborne_presentation'] is True and d['nov_airborne_presentation_authority']=='local_physics_ground_support' and d['animal_contact_search'] is True
assert d['animal_contact_search_authority']=='native_renderer_configured' and d['animal_contact_search_budget_ms']==5000
assert d['animal_native_context_collection'] is True and d['animal_observed_approach'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008FV_PUBLIC_OK',d['source_commit'])
PUBLIC_CHECK
echo "008FV_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Nov agora distingue caminhada, queda e retorno ao apoio físico na animação.'
