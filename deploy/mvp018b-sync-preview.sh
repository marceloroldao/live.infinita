#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
REQUIRED=e0aaf5170e6ee3eeed76156dfb89785adb010b74
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
RENDERER=live-infinita-renderer.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
fail(){ echo "MVP018B_SYNC_PREVIEW_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp018b-sync-preview.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout contém alterações rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize a main antes de instalar'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'MVP-018B não integrado à main'
for svc in "$WORLD" "$API" "$RENDERER" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Não atualizar API enquanto LIVE estiver transmitindo'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
echo "BEFORE world=$world_pid api=$api_pid renderer=$renderer_pid"
PYTHONPATH=.:apps/world-runtime:apps/audio-service:apps/audience "$INSTALL/.venv/bin/python" -m unittest tests.test_nov_episode_sync_preview tests.test_nov_life_observability tests.test_memoria_v2_cognitive_projection
bash -n "$REPO/deploy/mvp018b-sync-preview.sh"
node --check "$REPO/apps/manager/app.js"
echo '== Contrato somente local; nenhum envio à Memoria.ia central =='
sudo -v
backup="/var/backups/live-infinita/mvp018b-sync-preview-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
files=(apps/world-runtime/main_cognitive_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css packages/observability/nov_life.py)
for file in "${files[@]}"; do
    sudo cp -a "$INSTALL/$file" "$backup/$(basename "$file")"
done
module=packages/observability/nov_episode_sync.py
had_module=0
if [[ -f "$INSTALL/$module" ]]; then
    had_module=1
    sudo cp -a "$INSTALL/$module" "$backup/nov_episode_sync.py"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP018B_SYNC_PREVIEW_ROLLBACK: restaurando API e Manager; mundo intocado' >&2
        for file in "${files[@]}"; do
            sudo cp -a "$backup/$(basename "$file")" "$INSTALL/$file"
        done
        if (( had_module )); then
            sudo cp -a "$backup/nov_episode_sync.py" "$INSTALL/$module"
        else
            sudo rm -f "$INSTALL/$module"
        fi
        sudo systemctl restart "$API" || true
    fi
}
trap rollback EXIT
applied=1
for file in "${files[@]}" "$module"; do
    sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$file" "$INSTALL/$file"
    cmp "$REPO/$file" "$INSTALL/$file"
done
sudo "$INSTALL/.venv/bin/python" -m py_compile "$INSTALL/apps/world-runtime/main_cognitive_live.py" "$INSTALL/packages/observability/nov_life.py" "$INSTALL/$module"
node --check "$INSTALL/apps/manager/app.js"
started_at="$(date -u '+%Y-%m-%d %H:%M:%S')"
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
sleep 12
for svc in "$WORLD" "$API" "$RENDERER" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "$svc não recuperou'
    current_pid="$(systemctl show "$svc" -p MainPID --value)"
    [[ "$current_pid" =~ ^[0-9]+$ && "$current_pid" -gt 1 ]] || fail "$svc com PID inválido"
done
[[ "$(systemctl show "$WORLD" -p MainPID --value)" == "$world_pid" ]] || fail 'Single Writer reiniciou'
[[ "$(systemctl show "$API" -p MainPID --value)" != "$api_pid" ]] || fail 'API não reiniciou'
renderer_pid_after="$(systemctl show "$RENDERER" -p MainPID --value)"
if [[ "$renderer_pid_after" != "$renderer_pid" ]]; then
    journalctl -u "$RENDERER" --since "$started_at" --no-pager | grep -F '[render] native fast sky enabled' >/dev/null ||
        fail 'Renderer não confirmou shader otimizado após reinício transitivo'
fi
[[ "$(curl -sS --max-time 8 -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/api/manage/nov/sync/preview)" == 401 ]] ||
    fail 'Prévia de sincronização não está protegida por autenticação'
sudo "$INSTALL/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
from urllib.request import Request, urlopen
env=Path('/etc/live-infinita/operator.env').read_text()
token=next((line.partition('=')[2].strip() for line in env.splitlines()
           if line.startswith('LIVE_INFINITA_OPERATOR_TOKEN=')), '')
assert token, 'operator token absent'
url='http://127.0.0.1:8080/api/manage/nov/sync/preview?cursor=0'
with urlopen(Request(url,headers={'Authorization':'Bearer '+token}),timeout=12) as reply:
    value=json.load(reply)
assert value['schema']=='live-infinita-npc-episode-preview/v1'
assert value['transport_enabled'] is False
assert value['candidate_cursor_is_ack'] is False
assert value['central_receipt'] is None
assert value['world_mutated'] is False
assert value['selection_authority'] is False
assert value['world_id']=='nov-live-autonomous-001'
assert isinstance(value['episodes'],list) and value['episodes']
for row in value['episodes']:
    assert row['schema']=='live-infinita-npc-episode-observation/v1'
    assert row['source']['source_kind']=='need_outcome'
print('MVP018B_SYNC_PREVIEW_ENDPOINT_OK',
      'typed_episodes=',len(value['episodes']),
      'world_id=',value['world_id'],
      'candidate_cursor=',value['candidate_next_cursor'],
      'central_receipt=',value['central_receipt'])
PY
trap - EXIT
applied=0
echo "MVP018B_SYNC_PREVIEW_DEPLOY_OK world_pid=$world_pid renderer_pid=$renderer_pid_after"
echo 'MVP018B_SYNC_PREVIEW_FINISHED'
