#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
RUNTIME=/opt/live.infinita/apps/world-runtime
PUBLIC=/var/www/live-infinita-godot/navigation-memory/weather-memory.json
SERVICE=live-infinita-weather-control.service
TIMER=live-infinita-weather-control.timer
cd "$REPO"
LOG=/home/etbra/008dq1-weather-memory-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DQ1_START source=$SHA"
[ -z "$(git status --porcelain)" ] || { echo '008DQ1_ABORT: checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-physical-weather.timer
systemctl is-active --quiet "$TIMER"
[ -f /etc/live-infinita/memoria-local.env ]
[ -f "$RUNTIME/world_weather_control.py" ]
[ -f /var/lib/live-infinita/weather/control.json ]
BACKUP="/opt/live.infinita/.rollouts/008dq1-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "/etc/systemd/system/$SERVICE" "$BACKUP/$SERVICE"
if [ -f "$RUNTIME/world_weather_memory_experiment.py" ]; then cp -a "$RUNTIME/world_weather_memory_experiment.py" "$BACKUP/world_weather_memory_experiment.py"; fi
if [ -f "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/weather-memory.json"; fi
rollback() {
  rc=$?
  trap - ERR
  echo "008DQ1_ROLLBACK rc=$rc"
  systemctl stop "$TIMER" "$SERVICE" || true
  cp -a "$BACKUP/$SERVICE" "/etc/systemd/system/$SERVICE"
  if [ -f "$BACKUP/world_weather_memory_experiment.py" ]; then cp -a "$BACKUP/world_weather_memory_experiment.py" "$RUNTIME/world_weather_memory_experiment.py"; else rm -f "$RUNTIME/world_weather_memory_experiment.py"; fi
  if [ -f "$BACKUP/weather-memory.json" ]; then cp -a "$BACKUP/weather-memory.json" "$PUBLIC"; else rm -f "$PUBLIC"; fi
  rm -f "$RUNTIME/world_weather_memory_experiment.py.new-008dq1"
  systemctl daemon-reload || true
  systemctl start "$TIMER" || true
  echo 'Controle, previsões e memórias confirmadas foram preservados.'
  exit "$rc"
}
trap rollback ERR
systemctl stop "$TIMER" "$SERVICE"
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/world_weather_memory_experiment.py" "$RUNTIME/world_weather_memory_experiment.py.new-008dq1"
mv "$RUNTIME/world_weather_memory_experiment.py.new-008dq1" "$RUNTIME/world_weather_memory_experiment.py"
install -o root -g root -m 0644 "$REPO/deploy/live-infinita-weather-memory-experiment.service" "/etc/systemd/system/$SERVICE"
systemctl daemon-reload
systemctl start "$SERVICE"
systemctl start "$TIMER"
systemctl is-active --quiet "$TIMER"
python3 - <<'PY'
import json,time,urllib.request
p=json.load(open('/var/www/live-infinita-godot/navigation-memory/weather-memory.json'))
assert p['schema']=='live-infinita-weather-memory-experiment/v1'
assert p['inference_influence'] is False and p['world_write_authority'] is False
print('008DQ1_API_DIAGNOSTIC',p.get('last_api_failure'))
assert p['last_reason']!='memory_api_or_contract_unavailable', 'API da memória indisponível na instalação'
assert -30<=time.time()-p['generated_at_unix']<=30
url='https://live.etbra.com.br/godot/navigation-memory/weather-memory.json?verify='+str(int(time.time()))
with urllib.request.urlopen(url,timeout=20) as response: remote=json.load(response)
assert remote['schema']==p['schema'] and remote['world_id']==p['world_id']
assert -30<=time.time()-remote['generated_at_unix']<=30
print('008DQ1_PUBLIC_MEMORY_EXPERIMENT_OK',remote['recalled_memories'],remote['paired'],remote['last_reason'])
PY
echo "008DQ1_OK source=$SHA backup=$BACKUP"
echo 'Experimento ativo; exige três transições recuperadas antes da primeira previsão com memória.'
