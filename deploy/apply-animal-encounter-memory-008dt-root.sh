#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
RUNTIME=/opt/live.infinita/apps/world-runtime
WEB=/var/www/live-infinita-godot/world-map-preview
PUBLIC=/var/www/live-infinita-godot/wildlife
SERVICE=live-infinita-animal-memory.service
TIMER=live-infinita-animal-memory.timer
DROPIN=/etc/systemd/system/live-infinita-renderer.service.d/008dt-encounters.conf
cd "$REPO"
LOG=/home/etbra/008dt-animal-memory-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DT_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo '008DT_ABORT checkout precisa estar limpo'; exit 3; }
[ -f /etc/live-infinita/memoria-local.env ]
[ -f /var/lib/live-infinita/wildlife/state.json ]
[ -f "$RUNTIME/world_weather_memory_experiment.py" ]
systemctl is-active --quiet live-infinita-renderer.service
BACKUP="/opt/live.infinita/.rollouts/008dt-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_animal_encounters.gd world_map_preview.gd)
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
for f in "$SERVICE" "$TIMER"; do
  if [ -f "/etc/systemd/system/$f" ]; then cp -a "/etc/systemd/system/$f" "$BACKUP/$f"; fi
done
if [ -f "$DROPIN" ]; then cp -a "$DROPIN" "$BACKUP/dropin.conf"; fi
if [ -f "$RUNTIME/nov_animal_memory_sync.py" ]; then cp -a "$RUNTIME/nov_animal_memory_sync.py" "$BACKUP/nov_animal_memory_sync.py"; fi
if [ -f "$PUBLIC/encounter-memory.json" ]; then cp -a "$PUBLIC/encounter-memory.json" "$BACKUP/encounter-memory.json"; fi
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
WAS_ENABLED=0
if systemctl is-enabled --quiet "$TIMER" 2>/dev/null; then WAS_ENABLED=1; fi
rollback() {
  rc=$?; trap - ERR
  echo "008DT_ROLLBACK rc=$rc"
  systemctl disable --now "$TIMER" || true
  systemctl stop "$SERVICE" live-infinita-renderer.service || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  for f in "$SERVICE" "$TIMER"; do
    if [ -f "$BACKUP/$f" ]; then cp -a "$BACKUP/$f" "/etc/systemd/system/$f"; else rm -f "/etc/systemd/system/$f"; fi
  done
  if [ -f "$BACKUP/dropin.conf" ]; then cp -a "$BACKUP/dropin.conf" "$DROPIN"; else rm -f "$DROPIN"; fi
  if [ -f "$BACKUP/nov_animal_memory_sync.py" ]; then cp -a "$BACKUP/nov_animal_memory_sync.py" "$RUNTIME/nov_animal_memory_sync.py"; else rm -f "$RUNTIME/nov_animal_memory_sync.py"; fi
  if [ -f "$BACKUP/encounter-memory.json" ]; then cp -a "$BACKUP/encounter-memory.json" "$PUBLIC/encounter-memory.json"; else rm -f "$PUBLIC/encounter-memory.json"; fi
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl daemon-reload
  if [ "$WAS_ENABLED" -eq 1 ]; then systemctl enable --now "$TIMER" || true; fi
  systemctl restart live-infinita-renderer.service || true
  echo 'População, fila de encontros e memórias já gravadas foram preservadas.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
install -d -m 0755 "$(dirname "$DROPIN")"
cat > "$DROPIN" <<'CONF'
[Service]
Environment=LIVE_INFINITA_ENCOUNTERS_STATE=/var/lib/live-infinita/wildlife/encounters.json
Environment=LIVE_INFINITA_ENCOUNTERS_ACK=/var/lib/live-infinita/wildlife/encounters-ack.json
CONF
for f in "${FILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"; done
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_animal_memory_sync.py" "$RUNTIME/nov_animal_memory_sync.py"
for f in "$SERVICE" "$TIMER"; do install -o root -g root -m 0644 "$REPO/deploy/$f" "/etc/systemd/system/$f"; done
systemctl daemon-reload
systemctl restart live-infinita-renderer.service
python3 - <<'CHECK'
import pathlib,time,json,hashlib
path=pathlib.Path('/var/lib/live-infinita/wildlife/encounters.json')
for attempt in range(60):
    if path.exists() and time.time()-path.stat().st_mtime<10:break
    time.sleep(1)
else:raise RuntimeError('008DT gravador de encontros não publicou; verifique o journal')
envelope=json.loads(path.read_text())
assert hashlib.sha256(envelope['payload'].encode()).hexdigest()==envelope['sha256']
s=json.loads(envelope['payload'])
assert s['schema']=='live-infinita-nov-animal-encounters/v1'
assert s['source']=='local_physics_eye_sensor' and s['contains_prediction'] is False
assert path.stat().st_mode & 0o777 == 0o600
print('008DT_NATIVE_RECORDER_OK',s['world_id'],'pending',len(s['pending']))
CHECK
systemctl start "$SERVICE"
systemctl enable --now "$TIMER"
python3 - <<'CHECK'
import json,time,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/wildlife/encounter-memory.json?t='+str(time.time()),timeout=20) as r:s=json.load(r)
assert s['schema']=='live-infinita-nov-animal-memory/v1'
assert s['last_error'] is None, s['last_error']
assert time.time()-s['generated_at_unix']<30
assert s['decision_use'] is False and s['world_write_authority'] is False
print('008DT_MEMORY_BRIDGE_OK stored_and_recovered=',s['stored_and_recovered_encounters'])
print('Aguardar encontros reais é normal; nenhuma memória artificial é injetada.')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet "$TIMER"
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import json,sys,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json',timeout=20) as r:s=json.load(r)
assert s['source_commit']==sys.argv[1] and s['nov_eye_encounter_recording'] is True
assert s['nov_animal_memory_decision_use'] is False and s['physical_wildlife'] is True
assert s['resident_terrain_collision'] is True and s['physical_weather'] is True
print('008DT_PUBLIC_OK',s['source_commit'])
CHECK
echo "008DT_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Experiências vêm dos avistamentos; buscas e previsões entram depois.'
