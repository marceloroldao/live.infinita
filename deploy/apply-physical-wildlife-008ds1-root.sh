#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/renderer-godot
WEB=/var/www/live-infinita-godot/world-map-preview
PUBLIC=/var/www/live-infinita-godot/wildlife
PRIVATE=/var/lib/live-infinita/wildlife
SERVICE=live-infinita-renderer.service
DROPIN=/etc/systemd/system/live-infinita-renderer.service.d/008ds1-wildlife.conf
cd "$REPO"
LOG=/home/etbra/008ds1-wildlife-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DS1_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo '008DS1_ABORT checkout precisa estar limpo'; exit 3; }
[ -f "$DST/nov_visual_perception.gd" ]
BACKUP="/opt/live.infinita/.rollouts/008ds1-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=(nov_rabbit.gd world_map_wildlife.gd nov_visual_perception.gd world_map_preview.gd)
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
if [ -f "$DROPIN" ]; then cp -a "$DROPIN" "$BACKUP/dropin.conf"; fi
if [ -f "$PUBLIC/state.json" ]; then cp -a "$PUBLIC/state.json" "$BACKUP/public-state.json"; fi
cp -a "$WEB" "$BACKUP/world-map-preview"
cp -a /var/www/live-infinita-godot/index.html "$BACKUP/live-index.html"
cp -a /var/www/live-infinita-godot/build.json "$BACKUP/live-build.json"
rollback() {
  rc=$?; trap - ERR
  echo "008DS1_ROLLBACK rc=$rc"
  systemctl stop "$SERVICE" || true
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"; else rm -f "$DST/$f"; fi
  done
  if [ -f "$BACKUP/dropin.conf" ]; then cp -a "$BACKUP/dropin.conf" "$DROPIN"; else rm -f "$DROPIN"; fi
  if [ -f "$BACKUP/public-state.json" ]; then cp -a "$BACKUP/public-state.json" "$PUBLIC/state.json"; else rm -f "$PUBLIC/state.json"; fi
  rsync -a --delete "$BACKUP/world-map-preview/" "$WEB/" || true
  install -o www-data -g www-data -m 0644 "$BACKUP/live-index.html" /var/www/live-infinita-godot/index.html
  install -o www-data -g www-data -m 0644 "$BACKUP/live-build.json" /var/www/live-infinita-godot/build.json
  systemctl daemon-reload
  systemctl restart "$SERVICE" || true
  echo 'Checkpoint dos animais preservado para diagnóstico; não recriado.'
  exit "$rc"
}
trap rollback ERR
LIVE_INFINITA_SOURCE_SHA="$SHA" bash "$REPO/deploy/export-world-map-preview-web.sh"
install -d -o liveinfinita -g liveinfinita -m 0700 "$PRIVATE"
install -d -o liveinfinita -g www-data -m 0755 "$PUBLIC"
install -d -m 0755 "$(dirname "$DROPIN")"
cat > "$DROPIN" <<'CONF'
[Service]
Environment=LIVE_INFINITA_WILDLIFE_STATE=/var/lib/live-infinita/wildlife/state.json
Environment=LIVE_INFINITA_WILDLIFE_PUBLIC=/var/www/live-infinita-godot/wildlife/state.json
CONF
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/renderer-godot/$f" "$DST/$f"
done
systemctl daemon-reload
systemctl restart "$SERVICE"
python3 - "$SHA" <<'CHECK'
import json,sys,time,pathlib,urllib.request,hashlib
public=pathlib.Path('/var/www/live-infinita-godot/wildlife/state.json')
private=pathlib.Path('/var/lib/live-infinita/wildlife/state.json')
for attempt in range(60):
    if public.exists() and time.time()-public.stat().st_mtime<10:break
    time.sleep(1)
else:raise RuntimeError('008DS1 sem publicação recente dos animais; verifique WILDLIFE no journal')
b=json.loads(public.read_text())
assert b['authority']=='native_renderer_physics' and b['species']=='rabbit' and len(b['animals'])==3
assert b['learning'] is False and b['memory_writes'] is False
assert len({r['id'] for r in b['animals']})==3
assert time.time()-b['generated_at_unix']<10
p=json.loads(private.read_text())
assert hashlib.sha256(p['payload'].encode()).hexdigest()==p['sha256']
assert private.stat().st_mode & 0o777 == 0o600
assert public.stat().st_mode & 0o777 == 0o644
with urllib.request.urlopen('https://live.etbra.com.br/godot/wildlife/state.json',timeout=15) as r:remote=json.load(r)
assert remote['world_id']==b['world_id'] and len(remote['animals'])==3
print('008DS1_NATIVE_POPULATION_OK',b['world_id'],'count=3')
CHECK
systemctl is-active --quiet "$SERVICE"
bash "$REPO/deploy/promote-ready-world-live-008ca-root.sh"
python3 - "$SHA" <<'CHECK'
import json,sys,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/world-map-preview/build.json',timeout=20) as r:b=json.load(r)
assert b['source_commit']==sys.argv[1] and b['physical_wildlife'] is True
assert b['resident_terrain_collision'] is True and b['resident_terrain_collision_layer']==2
assert b['wildlife_population']==3 and b['wildlife_species']=='rabbit'
assert b['wildlife_authority']=='native_renderer_physics' and b['wildlife_learning'] is False
assert b['nov_visual_perception'] is True and b['live_physical_collision'] is True
assert b['physical_weather'] is True and b['weather_inference_influence'] is False
print('008DS1_PUBLIC_WILDLIFE_OK',b['source_commit'])
CHECK
echo "008DS1_OK source=$SHA backup=$BACKUP"
echo 'Recarregue a live. Três coelhos em habitat fixo; caça e memória dos encontros entram depois.'
