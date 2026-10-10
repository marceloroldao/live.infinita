#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
PYDST=/opt/live.infinita/apps/world-runtime
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008FG_ABORT checkout precisa estar limpo'; exit 3; }
for u in live-infinita-renderer.service live-infinita-memoria-local.service live-infinita-animal-approach.timer live-infinita-animal-search.timer; do systemctl is-active --quiet "$u"; done
cmp apps/world-runtime/nov_animal_approach_sync.py "$PYDST/nov_animal_approach_sync.py"
LOG=/home/etbra/008fg-animal-context-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008FG_START source=$SHA collection_only=true"
BACKUP="/opt/live.infinita/.rollouts/008fg-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FLAG_DIR=/etc/systemd/system/live-infinita-renderer.service.d
FLAG_FILE="$FLAG_DIR/99-animal-context-008fg.conf"
FILES=(nov_animal_context_history.gd nov_animal_approach.gd nov_animal_search_intent.gd world_map_local_motion.gd world_map_preview.gd)
PYFILES=(nov_animal_approach_context.py nov_animal_context_sync.py)
UNITS=(live-infinita-animal-context.service live-infinita-animal-context.timer)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
for f in "${PYFILES[@]}"; do if [ -f "$PYDST/$f" ]; then cp -a "$PYDST/$f" "$BACKUP/$f"; fi; done
for u in "${UNITS[@]}"; do if [ -f "/etc/systemd/system/$u" ]; then cp -a "/etc/systemd/system/$u" "$BACKUP/$u"; fi; done
if [ -f "$FLAG_FILE" ]; then cp -a "$FLAG_FILE" "$BACKUP/context.conf"; fi
PUBLIC=/var/www/live-infinita-godot/wildlife/context-core.json
if [ -f "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/context-core.json"; fi
TIMER_WAS_ENABLED=0
if systemctl is-enabled --quiet live-infinita-animal-context.timer 2>/dev/null; then TIMER_WAS_ENABLED=1; fi
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008FG_ROLLBACK rc=$rc"
  systemctl stop live-infinita-renderer.service || true
  systemctl disable --now live-infinita-animal-context.timer || true
  systemctl stop live-infinita-animal-context.service || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  for f in "${PYFILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$PYDST/$f"; else rm -f "$PYDST/$f"; fi
  done
  for u in "${UNITS[@]}"; do
    if [ -f "$BACKUP/$u" ]; then install -m 0644 "$BACKUP/$u" "/etc/systemd/system/$u"; else rm -f "/etc/systemd/system/$u"; fi
  done
  if [ -f "$BACKUP/context.conf" ]; then install -m 0644 "$BACKUP/context.conf" "$FLAG_FILE"; else rm -f "$FLAG_FILE"; fi
  if [ -f "$BACKUP/context-core.json" ]; then cp -a "$BACKUP/context-core.json" "$PUBLIC"; else rm -f "$PUBLIC"; fi
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl daemon-reload || true
  if [ "$TIMER_WAS_ENABLED" = 1 ]; then systemctl enable --now live-infinita-animal-context.timer || true; fi
  systemctl restart live-infinita-renderer.service || true
  echo 'Memórias, contexto privado, animais e histórico preservados.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_NAVIGATION_COST_SHIFT=1 LIVE_INFINITA_NAVIGATION_CONTACT_TURNS=1 LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION=1 LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE=1 LIVE_INFINITA_ANIMAL_APPROACH_ENABLED=1 LIVE_INFINITA_ANIMAL_CONTEXT_ENABLED=1 LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
systemctl stop live-infinita-renderer.service
systemctl stop live-infinita-animal-context.timer 2>/dev/null || true
systemctl stop live-infinita-animal-context.service 2>/dev/null || true
for f in "${FILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"; cmp "$REPO/apps/renderer-godot/$f" "$DST/$f"; done
for f in "${PYFILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/$f" "$PYDST/$f"; cmp "$REPO/apps/world-runtime/$f" "$PYDST/$f"; done
for u in "${UNITS[@]}"; do install -m 0644 "$REPO/deploy/$u" "/etc/systemd/system/$u"; done
mkdir -p "$FLAG_DIR"
printf '[Service]\nEnvironment=LIVE_INFINITA_ANIMAL_CONTEXT_ENABLED=1\n' > "$FLAG_FILE"
systemctl daemon-reload
RESTART_AT="$(python3 -c 'import time; print(time.time())')"
systemctl restart live-infinita-renderer.service
python3 - "$RESTART_AT" <<'NATIVE_CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
for _ in range(60):
    try:
        d=json.loads(p.read_text());a=d['approach'];c=a['context_history']
        assert d['generated_at_unix']>=float(sys.argv[1]) and -5<time.time()-d['generated_at_unix']<10
        assert d.get('last_error') is None and d['source']=='native_bounded_animal_search' and d['world_write_authority'] is False
        assert a['enabled'] is True and a['history']['storage_ready'] is True and a['history']['persistent'] is True
        assert c['collection_enabled'] is True and c['storage_ready'] is True and c['persistent'] is True
        assert c['profile']=='capsule044-height18-sweep4-native-contour-v1' and c['decision_use'] is False and c['last_error']==''
        print('008FG_NATIVE_OK',c);break
    except (OSError,ValueError,KeyError,TypeError,AssertionError):time.sleep(1)
else:raise RuntimeError('Coleta nativa não publicou estado recente e saudável')
NATIVE_CHECK
systemctl enable --now live-infinita-animal-context.timer
systemctl start live-infinita-animal-context.service
[ "$(systemctl show live-infinita-animal-context.service -p Result --value)" = success ]
python3 - "$RESTART_AT" <<'CORE_CHECK'
import pathlib,json,time,sys
d=json.loads(pathlib.Path('/var/www/live-infinita-godot/wildlife/context-core.json').read_text())
assert d['schema']=='live-infinita-native-contextual-approach-core-status/v1'
assert d['generated_at_unix']>=float(sys.argv[1]) and -5<time.time()-d['generated_at_unix']<180
assert d['source']=='memoria.ia-local-structural-api' and d['profile']=='capsule044-height18-sweep4-native-contour-v1'
assert d['decision_use'] is False and d['world_write_authority'] is False and d['capture'] is False
for k in ('eligible_in_source','confirmed_total','cached_recovered','acked_this_poll','recovered_this_poll'):
    assert type(d[k]) is int and d[k]>=0
if d['eligible_in_source']>0:assert d['confirmed_total']>0 and d['cached_recovered']>0
print('008FG_CORE_OK',d)
CORE_CHECK
for u in live-infinita-renderer.service live-infinita-memoria-local.service live-infinita-animal-approach.timer live-infinita-animal-context.timer live-infinita-animal-search.timer; do systemctl is-active --quiet "$u"; done
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'PUBLIC_CHECK'
import urllib.request,json,time,sys
d=json.load(urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20))
assert d['source_commit']==sys.argv[1] and d['animal_native_context_collection'] is True
assert d['animal_approach_durable_history'] is True and d['animal_observed_approach'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008FG_PUBLIC_OK',d['source_commit'])
PUBLIC_CHECK
echo "008FG_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Contexto da aproximação nativa em coleta; seleção de alvo preservada.'
