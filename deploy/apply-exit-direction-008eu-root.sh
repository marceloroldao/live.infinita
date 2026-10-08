#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008EU_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-memory.timer
systemctl is-active --quiet live-infinita-animal-search.timer
grep -q 'OBSERVED_CELL_M' "$DST/nov_stuck_recovery.gd"
grep -q 'contour.filter' "$DST/nov_navigation_experience.gd"
grep -q 'NOV_JOURNEY_ATTEMPT' apps/renderer-godot/nov_navigation_journey.gd
systemctl is-active --quiet live-infinita-memoria-local.service
LOG=/home/etbra/008eu-exit-direction-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008EU_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008eu-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FLAG_DIR=/etc/systemd/system/live-infinita-renderer.service.d
FLAG_FILE="$FLAG_DIR/99-navigation-exit-direction-008eu.conf"
if [ -f "$FLAG_FILE" ]; then cp -a "$FLAG_FILE" "$BACKUP/exit-direction.conf"; fi
FILES=(nov_navigation_experience.gd nov_navigation_contour.gd nov_navigation_patterns.gd nov_navigation_pattern_collector.gd nov_navigation_episodes.gd nov_navigation_journey.gd world_map_local_motion.gd world_map_preview.gd)
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
  echo "008EU_ROLLBACK rc=$rc"
  systemctl disable --now live-infinita-navigation-pattern.timer || true
  systemctl stop live-infinita-navigation-pattern.service || true
  for unit in live-infinita-navigation-pattern.service live-infinita-navigation-pattern.timer; do
    if [ -f "$BACKUP/$unit" ]; then install -m 0644 "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  if [ -f "$BACKUP/$PYFILE" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$PYFILE" "/opt/live.infinita/apps/world-runtime/$PYFILE"; else rm -f "/opt/live.infinita/apps/world-runtime/$PYFILE"; fi
  if [ -f "$BACKUP/exit-direction.conf" ]; then install -m 0644 "$BACKUP/exit-direction.conf" "$FLAG_FILE"; else rm -f "$FLAG_FILE"; fi
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
systemctl stop live-infinita-navigation-pattern.timer
systemctl stop live-infinita-navigation-pattern.service
LIVE_INFINITA_NAVIGATION_COST_SHIFT=1 LIVE_INFINITA_NAVIGATION_CONTACT_TURNS=1 LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION=1 LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
  cmp "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/$PYFILE" "/opt/live.infinita/apps/world-runtime/$PYFILE"
for unit in live-infinita-navigation-pattern.service live-infinita-navigation-pattern.timer; do
  install -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
mkdir -p "$FLAG_DIR"
printf '[Service]\nEnvironment=LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION=1\n' > "$FLAG_FILE"
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
            print('008EU_NATIVE_OK',d['counts'])
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
        p=json.loads((root/'nov-navigation-patterns-008ej.json').read_text())
        assert p['schema']=='live-infinita-native-pattern-outcomes/v2'
        assert p['profile']=='capsule044-height18-lookahead3-contour64-localexit-v3'
        assert d['patterns'].get('cost_shift_enabled') is True
        assert d['patterns'].get('local_turn_continuity_enabled') is True
        assert d['patterns'].get('exit_direction_enabled') is True
        assert 'decision_reasons' in d['patterns'] and 'last_evaluation' in d['patterns']
        print('008EU_COLLECTOR_READY',d['patterns'])
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
assert d['navigation_local_contour_feedback'] is True
assert d['navigation_local_cost_scale_m']==3.0
assert d['navigation_pattern_decision_diagnostics'] is True
assert d['navigation_pattern_contact_lifecycle'] is True
assert d['navigation_adaptive_cost_windows'] is True
assert d['navigation_local_turn_continuity'] is True
assert d['navigation_exit_direction_gate'] is True
assert d['navigation_journey_attempt_telemetry'] is True
assert d['navigation_stuck_recovery'] is True and d['nov_animal_search_bounded_intent'] is True
assert d['narrator_caption_position']=='center' and d['live_exploration_controls'] is False
print('008EU_PUBLIC_OK',d['source_commit'])
CHECK
echo "008EU_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Seleção de saída física ativa; memória preservada. Para desligar: sudo bash /home/etbra/set-exit-direction-008eu-root.sh off'
