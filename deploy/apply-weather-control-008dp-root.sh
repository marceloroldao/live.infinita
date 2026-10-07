#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
RUNTIME=/opt/live.infinita/apps/world-runtime
PUBLIC=/var/www/live-infinita-godot/navigation-memory/weather-control.json
SERVICE=live-infinita-weather-control.service
TIMER=live-infinita-weather-control.timer
cd "$REPO"
LOG=/home/etbra/008dp-weather-control-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DP_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo '008DP_ABORT: checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-physical-weather.timer
[ -d /var/lib/live-infinita/weather ]
[ -d /var/www/live-infinita-godot/navigation-memory ]
python3 - <<'PY'
import json
b=json.load(open('/var/www/live-infinita-godot/world-map-preview/build.json'))
assert b.get('physical_weather') is True, 'Instale 008DO primeiro'
PY
BACKUP="/opt/live.infinita/.rollouts/008dp-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
if [ -f "$RUNTIME/world_weather_control.py" ]; then cp -a "$RUNTIME/world_weather_control.py" "$BACKUP/world_weather_control.py"; fi
for unit in "$SERVICE" "$TIMER"; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; fi
done
if systemctl is-enabled --quiet "$TIMER"; then touch "$BACKUP/timer-enabled"; fi
if systemctl is-active --quiet "$TIMER"; then touch "$BACKUP/timer-active"; fi
if [ -f "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/weather-control.json"; fi
rollback() {
  rc=$?
  trap - ERR
  echo "008DP_ROLLBACK rc=$rc"
  systemctl stop "$TIMER" "$SERVICE" || true
  systemctl disable "$TIMER" || true
  for unit in "$SERVICE" "$TIMER"; do
    if [ -f "$BACKUP/$unit" ]; then cp -a "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  if [ -f "$BACKUP/world_weather_control.py" ]; then cp -a "$BACKUP/world_weather_control.py" "$RUNTIME/world_weather_control.py"; else rm -f "$RUNTIME/world_weather_control.py"; fi
  if [ -f "$BACKUP/weather-control.json" ]; then cp -a "$BACKUP/weather-control.json" "$PUBLIC"; else rm -f "$PUBLIC"; fi
  rm -f "$RUNTIME/world_weather_control.py.new-008dp"
  systemctl daemon-reload || true
  if [ -f "$BACKUP/timer-enabled" ]; then systemctl enable "$TIMER" || true; fi
  if [ -f "$BACKUP/timer-active" ]; then systemctl start "$TIMER" || true; fi
  echo 'Checkpoint privado preservado para manter previsões já emitidas.'
  exit "$rc"
}
trap rollback ERR
for unit in "$TIMER" "$SERVICE"; do
  if systemctl cat "$unit" >/dev/null 2>&1; then systemctl stop "$unit"; fi
done
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/world_weather_control.py" "$RUNTIME/world_weather_control.py.new-008dp"
mv "$RUNTIME/world_weather_control.py.new-008dp" "$RUNTIME/world_weather_control.py"
for unit in "$SERVICE" "$TIMER"; do
  install -o root -g root -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl start "$SERVICE"
systemctl enable --now "$TIMER"
systemctl is-active --quiet "$TIMER"
python3 - <<'PY'
import json,time,urllib.request
path='/var/www/live-infinita-godot/navigation-memory/weather-control.json'
p=json.load(open(path))
assert p['schema']=='live-infinita-weather-control/v1'
assert p['method']=='persistence_control'
assert p['memory_used'] is False and p['nov_prediction'] is False
assert p['horizon_ms']==60000 and p['pending'] is not None
assert -30<=time.time()-p['generated_at_unix']<=30
url='https://live.etbra.com.br/godot/navigation-memory/weather-control.json?check='+str(int(time.time()))
with urllib.request.urlopen(url,timeout=20) as response: remote=json.load(response)
assert remote['schema']==p['schema'] and remote['world_id']==p['world_id']
assert -30<=time.time()-remote['generated_at_unix']<=30
print('008DP_PUBLIC_CONTROL_OK',remote['evaluated'],remote['missed'],remote['pending']['prediction_id'])
PY
echo "008DP_OK source=$SHA backup=$BACKUP"
echo 'Controle prospectivo pronto; primeira avaliação após 60 segundos lógicos.'
