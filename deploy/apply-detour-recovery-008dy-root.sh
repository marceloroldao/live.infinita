#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008DY_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-memory.timer
systemctl is-active --quiet live-infinita-animal-search.timer
grep -q 'OBSERVED_CELL_M' apps/renderer-godot/nov_stuck_recovery.gd
LOG=/home/etbra/008dy-detour-recovery-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DY_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008dy-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "$DST/nov_stuck_recovery.gd" "$BACKUP/nov_stuck_recovery.gd"
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008DY_ROLLBACK rc=$rc"
  install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/nov_stuck_recovery.gd" "$DST/nov_stuck_recovery.gd"
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl restart live-infinita-renderer.service || true
  echo 'Memórias, encontros, animais e histórico de buscas preservados.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/nov_stuck_recovery.gd" "$DST/nov_stuck_recovery.gd"
cmp "$REPO/apps/renderer-godot/nov_stuck_recovery.gd" "$DST/nov_stuck_recovery.gd"
systemctl restart live-infinita-renderer.service
python3 - <<'CHECK'
import pathlib,json,time
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
for _ in range(60):
    try:
        d=json.loads(p.read_text())
        if -5<time.time()-d.get('generated_at_unix',0)<10 and d.get('last_error') is None:
            assert d['source']=='native_bounded_animal_search' and d['world_write_authority'] is False
            print('008DY_NATIVE_OK',d['counts'])
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
assert d['navigation_stuck_recovery'] is True and d['nov_animal_search_bounded_intent'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008DY_PUBLIC_OK',d['source_commit'])
CHECK
echo "008DY_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Desvios por áreas novas não provocam retorno apenas por distância ao objetivo.'
