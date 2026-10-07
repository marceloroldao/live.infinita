#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008EH_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-memory.timer
systemctl is-active --quiet live-infinita-animal-search.timer
grep -q 'OBSERVED_CELL_M' "$DST/nov_stuck_recovery.gd"
grep -q 'contour.filter' "$DST/nov_navigation_experience.gd"
grep -q 'NOV_JOURNEY_ATTEMPT' apps/renderer-godot/nov_navigation_journey.gd
systemctl is-active --quiet live-infinita-memoria-local.service
LOG=/home/etbra/008eh-native-patterns-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008EH_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008eh-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_navigation_contour.gd nov_navigation_patterns.gd nov_navigation_pattern_collector.gd nov_navigation_journey.gd world_map_local_motion.gd world_map_preview.gd)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
PYFILE=nov_navigation_pattern_sync.py
if [ -f "/opt/live.infinita/apps/world-runtime/$PYFILE" ]; then cp -a "/opt/live.infinita/apps/world-runtime/$PYFILE" "$BACKUP/$PYFILE"; fi
TIMER_WAS_ENABLED=0
if systemctl is-enabled --quiet live-infinita-navigation-pattern.timer 2>/dev/null; then TIMER_WAS_ENABLED=1; fi
for unit in live-infinita-navigation-pattern.service live-infinita-navigation-pattern.timer; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; fi
done
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008EH_ROLLBACK rc=$rc"
  systemctl disable --now live-infinita-navigation-pattern.timer || true
  systemctl stop live-infinita-navigation-pattern.service || true
  for unit in live-infinita-navigation-pattern.service live-infinita-navigation-pattern.timer; do
    if [ -f "$BACKUP/$unit" ]; then install -m 0644 "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  if [ -f "$BACKUP/$PYFILE" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$PYFILE" "/opt/live.infinita/apps/world-runtime/$PYFILE"; else rm -f "/opt/live.infinita/apps/world-runtime/$PYFILE"; fi
  systemctl daemon-reload || true
  if [ "$TIMER_WAS_ENABLED" = 1 ]; then systemctl enable --now live-infinita-navigation-pattern.timer || true; fi
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
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/$PYFILE" "/opt/live.infinita/apps/world-runtime/$PYFILE"
for unit in live-infinita-navigation-pattern.service live-infinita-navigation-pattern.timer; do
  install -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
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
            print('008EH_NATIVE_OK',d['counts'])
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
python3 - "$RESTART_AT" <<'PATTERN_CHECK'
import pathlib,json,time,sys
root=pathlib.Path('/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase')
for _ in range(60):
    try:
        d=json.loads((root/'nov-learning-status-008df.json').read_text())
        assert d.get('observed_at_unix',0)>=int(sys.argv[1]) and d.get('patterns',{}).get('enabled') is True
        p=json.loads((root/'nov-navigation-patterns-008eh.json').read_text())
        assert p['schema']=='live-infinita-native-pattern-outcomes/v1'
        print('008EH_COLLECTOR_READY',d['patterns'])
        break
    except (OSError,ValueError,AssertionError):
        time.sleep(1)
else:
    raise RuntimeError('Coletor nativo de padrões não ficou pronto')
PATTERN_CHECK
systemctl enable --now live-infinita-navigation-pattern.timer
systemctl start live-infinita-navigation-pattern.service
[ "$(systemctl show live-infinita-navigation-pattern.service -p Result --value)" = success ]
systemctl is-active --quiet live-infinita-navigation-pattern.timer
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import urllib.request,json,time,sys
d=json.load(urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20))
assert d['source_commit']==sys.argv[1]
assert d['navigation_detour_progress_observed_cells'] is True
assert d['navigation_local_observed_contour'] is True
assert d['navigation_bidirectional_contour'] is True
assert d['navigation_native_pattern_outcomes'] is True
assert d['navigation_pattern_core_bridge'] is True
assert d['navigation_journey_attempt_telemetry'] is True
assert d['navigation_stuck_recovery'] is True and d['nov_animal_search_bounded_intent'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008EH_PUBLIC_OK',d['source_commit'])
CHECK
echo "008EH_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Nov registra padrões físicos; a ponte confirma armazenamento e recuperação no núcleo local.'
