#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008DV_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-search.timer
systemctl is-active --quiet live-infinita-animal-memory.timer
[ -f /var/www/live-infinita-godot/wildlife/search-predictions.json ]
LOG=/home/etbra/008dv-animal-panel-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DV_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008dv-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_animal_search_panel.gd world_map_hud.gd world_map_preview.gd)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008DV_ROLLBACK rc=$rc"
  systemctl stop live-infinita-renderer.service || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl restart live-infinita-renderer.service || true
  echo 'Memórias, previsões, fila de encontros e população foram preservadas.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"; done
systemctl restart live-infinita-renderer.service
python3 - <<'CHECK'
import json,time,pathlib
path=pathlib.Path('/var/lib/live-infinita/wildlife/encounters.json')
for attempt in range(60):
    if path.exists() and time.time()-path.stat().st_mtime<10:break
    time.sleep(1)
else:raise RuntimeError('008DV renderer não retomou o gravador de encontros')
path=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-predictions.json')
s=json.loads(path.read_text())
assert s['last_error'] is None and time.time()-s['generated_at_unix']<30
assert s['decision_use'] is False and s['world_write_authority'] is False
print('008DV_RENDERER_AND_FORECAST_OK')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-search.timer
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import json,time,sys,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20) as r:s=json.load(r)
assert s['source_commit']==sys.argv[1]
assert s['nov_animal_search_panel'] is True and s['nov_animal_search_shadow_evaluation'] is True
assert s['nov_animal_memory_decision_use'] is False
assert s['live_exploration_controls'] is False and s['narrator_caption_position']=='center'
print('008DV_PUBLIC_OK',s['source_commit'])
CHECK
echo "008DV_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live: o painel mostra encontros lembrados, regiões previstas e comparações reais.'
