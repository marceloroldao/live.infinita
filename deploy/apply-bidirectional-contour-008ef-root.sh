#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008EF_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-memory.timer
systemctl is-active --quiet live-infinita-animal-search.timer
grep -q 'OBSERVED_CELL_M' "$DST/nov_stuck_recovery.gd"
grep -q 'contour.filter' "$DST/nov_navigation_experience.gd"
grep -q 'NOV_JOURNEY_ATTEMPT' apps/renderer-godot/nov_navigation_journey.gd
LOG=/home/etbra/008ef-bidirectional-contour-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008EF_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008ef-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_navigation_contour.gd)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008EF_ROLLBACK rc=$rc"
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl restart live-infinita-renderer.service || true
  echo 'Memórias, encontros, animais e histórico de buscas preservados.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
  cmp "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
RESTART_AT="$(date +%s)"
systemctl restart live-infinita-renderer.service
python3 - "$RESTART_AT" <<'CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
for _ in range(60):
    try:
        d=json.loads(p.read_text())
        if d.get('generated_at_unix',0)>=int(sys.argv[1]) and -5<time.time()-d.get('generated_at_unix',0)<10 and d.get('last_error') is None:
            assert d['source']=='native_bounded_animal_search' and d['world_write_authority'] is False
            print('008EF_NATIVE_OK',d['counts'])
            break
    except (OSError,ValueError):
        pass
    time.sleep(1)
else:
    raise RuntimeError('Renderer não publicou estado recente após reinício')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-memory.timer
systemctl is-active --quiet live-infinita-animal-search.timer
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import urllib.request,json,time,sys
d=json.load(urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20))
assert d['source_commit']==sys.argv[1]
assert d['navigation_detour_progress_observed_cells'] is True
assert d['navigation_local_observed_contour'] is True
assert d['navigation_bidirectional_contour'] is True
assert d['navigation_journey_attempt_telemetry'] is True
assert d['navigation_stuck_recovery'] is True and d['nov_animal_search_bounded_intent'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008EF_PUBLIC_OK',d['source_commit'])
CHECK
echo "008EF_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Nov agora alterna excursões locais quando o contorno se prolonga.'
