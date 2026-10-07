#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
DROPIN=/etc/systemd/system/live-infinita-renderer.service.d/008dw-animal-search.conf
PRIVATE=/var/lib/live-infinita/wildlife/search-policy.json
PUBLIC=/var/www/live-infinita-godot/wildlife/search-intent.json
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008DW_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-search.timer
systemctl is-active --quiet live-infinita-animal-memory.timer
[ -f /var/lib/live-infinita/wildlife/search-predictions.json ]
LOG=/home/etbra/008dw-animal-search-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DW_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008dw-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_animal_search_intent.gd nov_animal_search_panel.gd world_map_preview.gd)
for f in "${FILES[@]}"; do if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi; done
if [ -f "$DROPIN" ]; then cp -a "$DROPIN" "$BACKUP/dropin.conf"; fi
if [ -f "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/search-intent.json"; fi
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008DW_ROLLBACK rc=$rc"
  systemctl stop live-infinita-renderer.service || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  if [ -f "$BACKUP/dropin.conf" ]; then cp -a "$BACKUP/dropin.conf" "$DROPIN"; else rm -f "$DROPIN"; fi
  if [ -f "$BACKUP/search-intent.json" ]; then cp -a "$BACKUP/search-intent.json" "$PUBLIC"; else rm -f "$PUBLIC"; fi
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl daemon-reload
  systemctl restart live-infinita-renderer.service || true
  echo 'Encontros, memórias, população e histórico privado das tentativas foram preservados.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
install -d -m 0755 "$(dirname "$DROPIN")"
cat > "$DROPIN" <<'CONF'
[Service]
Environment=LIVE_INFINITA_ANIMAL_SEARCH_ENABLED=1
Environment=LIVE_INFINITA_ANIMAL_SEARCH_POLICY=/var/lib/live-infinita/wildlife/search-policy.json
Environment=LIVE_INFINITA_ANIMAL_SEARCH_PUBLIC=/var/www/live-infinita-godot/wildlife/search-intent.json
Environment=LIVE_INFINITA_ANIMAL_SEARCH_SOURCE=/var/lib/live-infinita/wildlife/search-predictions.json
CONF
for f in "${FILES[@]}"; do install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"; done
systemctl daemon-reload
systemctl restart live-infinita-renderer.service
python3 - <<'CHECK'
import json,time,pathlib,hashlib
private=pathlib.Path('/var/lib/live-infinita/wildlife/search-policy.json')
public=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
for attempt in range(60):
    if public.exists():
        s=json.loads(public.read_text())
        if time.time()-s.get('generated_at_unix',0)<10 and s.get('last_error') is None:break
    time.sleep(1)
else:raise RuntimeError('008DW controlador não publicou estado válido')
assert s['schema']=='live-infinita-nov-animal-search-intent/v1'
assert s['source']=='native_bounded_animal_search'
assert s['decision_use'] is True and s['world_write_authority'] is False and s['absence_claim'] is False
assert private.stat().st_mode & 0o777 == 0o600
assert public.stat().st_mode & 0o777 == 0o644
envelope=json.loads(private.read_text())
assert hashlib.sha256(envelope['payload'].encode()).hexdigest()==envelope['sha256']
policy=json.loads(envelope['payload'])
assert policy['world_id']==s['world_id'] and policy['schema']=='live-infinita-nov-animal-search-policy/v1'
assert policy['cycle_starts']<=4
print('008DW_NATIVE_OK active=',s['active'],'counts=',s['counts'])
print('Aguardar região próxima, previsão válida e término da caminhada é normal.')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-animal-search.timer
systemctl is-active --quiet live-infinita-animal-memory.timer
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import json,time,sys,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json?t='+str(time.time()),timeout=20) as r:s=json.load(r)
assert s['source_commit']==sys.argv[1] and s['nov_animal_search_bounded_intent'] is True
assert s['nov_animal_search_native_authority'] is True
assert s['nov_animal_memory_decision_use'] is True
assert s['nov_animal_search_cycle_limit']==4 and s['nov_animal_search_attempt_budget_ms']==45000
assert s['nov_animal_search_panel'] is True and s['live_exploration_controls'] is False
with urllib.request.urlopen('https://live.etbra.com.br/godot/wildlife/search-intent.json?t='+str(time.time()),timeout=20) as r:status=json.load(r)
assert status['last_error'] is None and time.time()-status['generated_at_unix']<30
assert status['decision_use'] is True and status['world_write_authority'] is False
print('008DW_PUBLIC_OK',s['source_commit'])
CHECK
echo "008DW_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Buscas limitadas alternam memória e último local, confirmadas somente pela visão.'
