#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
REQUIRED=45043e52c374b643ff9957cd9092c7e15a0ec445
API=live-infinita.service
WORLD=live-infinita-autonomous-world.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
RENDERER=live-infinita-renderer.service
fail(){ echo "MVP018A_NOV_LIFE_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp018a-nov-life.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout com alterações locais rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize a main primeiro'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'MVP-018A não integrado à main'
for svc in "$API" "$WORLD" "$AUDIO" "$RELAY" "$RENDERER"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Transmissão ativa: não reiniciar API durante LIVE'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
echo "BEFORE world=$world_pid renderer=$renderer_pid api=$api_pid"

PYTHONPATH=.:apps/world-runtime:apps/audio-service:apps/audience "$INSTALL/.venv/bin/python" -m unittest tests.test_nov_life_observability tests.test_manager_performance_contract tests.test_npc_episodic_memory
bash -n "$REPO/deploy/mvp018a-nov-life.sh"
node --check "$REPO/apps/manager/app.js"
sudo -v
backup="/var/backups/live-infinita/mvp018a-nov-life-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
for file in apps/world-runtime/main_cognitive_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css; do
    sudo cp -a "$INSTALL/$file" "$backup/$(basename "$file")"
done
had_module=0
if [[ -f "$INSTALL/packages/observability/nov_life.py" ]]; then
    had_module=1
    sudo cp -a "$INSTALL/packages/observability/nov_life.py" "$backup/nov_life.py"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP018A_NOV_LIFE_ROLLBACK: apenas API e Manager' >&2
        for file in apps/world-runtime/main_cognitive_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css; do
            sudo cp -a "$backup/$(basename "$file")" "$INSTALL/$file"
        done
        if (( had_module )); then
            sudo cp -a "$backup/nov_life.py" "$INSTALL/packages/observability/nov_life.py"
        else
            sudo rm -f "$INSTALL/packages/observability/nov_life.py"
        fi
        sudo systemctl restart "$API" || true
    fi
}
trap rollback EXIT
applied=1
for file in apps/world-runtime/main_cognitive_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css packages/observability/nov_life.py; do
    sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$file" "$INSTALL/$file"
    cmp "$REPO/$file" "$INSTALL/$file"
done
sudo "$INSTALL/.venv/bin/python" -m py_compile "$INSTALL/apps/world-runtime/main_cognitive_live.py" "$INSTALL/packages/observability/nov_life.py"
node --check "$INSTALL/apps/manager/app.js"
sudo systemctl restart "$API"
ready=0
for attempt in $(seq 1 20); do
    if systemctl is-active --quiet "$API" &&
       curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:8080/api/health 2>/dev/null; then
        ready=1; break
    fi
    sleep 2
done
(( ready )) || fail 'API não retomou'
sleep 10
for svc in "$API" "$AUDIO" "$RELAY" "$WORLD" "$RENDERER"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo após deploy"
done
[[ "$(systemctl show "$WORLD" -p MainPID --value)" == "$world_pid" ]] || fail 'Single Writer reiniciou'
[[ "$(systemctl show "$RENDERER" -p MainPID --value)" == "$renderer_pid" ]] || fail 'Renderer reiniciou'
[[ "$(systemctl show "$API" -p MainPID --value)" != "$api_pid" ]] || fail 'API não reiniciou'
[[ "$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/manage/nov/life)" == 401 ]] ||
    fail 'Endpoint de Nov não está protegido'
sudo "$INSTALL/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
from urllib.request import Request, urlopen
env=Path('/etc/live-infinita/operator.env').read_text()
token=next((line.partition('=')[2].strip() for line in env.splitlines()
           if line.startswith('LIVE_INFINITA_OPERATOR_TOKEN=')), '')
assert token, 'operator token absent'
url='http://127.0.0.1:8080/api/manage/nov/life'
with urlopen(Request(url,headers={'Authorization':'Bearer '+token}),timeout=12) as reply:
    payload=json.load(reply)
assert payload.get('ok') and payload.get('mode')=='read-only-local-episodes'
assert payload.get('world_mutated') is False
assert payload.get('selection_authority') is False
assert payload.get('central_memoria_sync') is False
assert isinstance(payload.get('episodes'),list)
print('MVP018A_NOV_LIFE_ENDPOINT_OK',
      'ledger_available=',payload.get('ledger_available'),
      'recent_episodes=',len(payload['episodes']),
      'latest_tick=',payload.get('latest_episode_tick'))
PY
trap - EXIT
applied=0
echo "MVP018A_NOV_LIFE_DEPLOY_OK world_pid=$world_pid renderer_pid=$renderer_pid"
echo 'MVP018A_NOV_LIFE_FINISHED'
