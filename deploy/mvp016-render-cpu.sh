#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
REQUIRED=d72e041e9c7f1dde5feecb7d12aa410346da88f7
RENDERER=live-infinita-renderer.service
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
fail(){ echo "MVP016_RENDER_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp016-render-cpu.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout com alterações rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize checkout primeiro'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'MVP-016 não integrado à main'
for svc in "$WORLD" "$API" "$AUDIO" "$RENDERER"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Broadcaster ativo: não modificar renderização durante transmissão'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
echo "BEFORE: world=$world_pid api=$api_pid audio=$audio_pid renderer=$renderer_pid"
echo '== Testes =='
"$INSTALL/.venv/bin/python" -m unittest tests.test_headless_renderer
bash -n "$REPO/deploy/mvp016-render-cpu.sh"
sudo -v
backup="/var/backups/live-infinita/mvp016-render-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
sudo cp -a "$INSTALL/apps/headless-renderer/headless_renderer.py" "$backup/headless_renderer.py"
sudo cp -a "$INSTALL/apps/renderer-godot/main.gd" "$backup/main.gd"
sudo cp -a "/etc/systemd/system/$RENDERER" "$backup/$RENDERER"
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP016_RENDER_ROLLBACK: apenas renderer e unit' >&2
        sudo cp -a "$backup/headless_renderer.py" "$INSTALL/apps/headless-renderer/headless_renderer.py"
        sudo cp -a "$backup/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
        sudo cp -a "$backup/$RENDERER" "/etc/systemd/system/$RENDERER"
        sudo systemctl daemon-reload
        sudo systemctl restart "$RENDERER" || true
    fi
}
trap rollback EXIT
applied=1
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/headless-renderer/headless_renderer.py" "$INSTALL/apps/headless-renderer/headless_renderer.py"
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/renderer-godot/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
sudo install -m 0644 "$REPO/deploy/$RENDERER" "/etc/systemd/system/$RENDERER"
cmp "$REPO/apps/headless-renderer/headless_renderer.py" "$INSTALL/apps/headless-renderer/headless_renderer.py"
cmp "$REPO/apps/renderer-godot/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
cmp "$REPO/deploy/$RENDERER" "/etc/systemd/system/$RENDERER"
sudo "$INSTALL/.venv/bin/python" -m py_compile "$INSTALL/apps/headless-renderer/headless_renderer.py"
sudo -u liveinfinita "$INSTALL/.venv/bin/python" "$INSTALL/apps/headless-renderer/headless_renderer.py" --dry-run
sudo systemctl daemon-reload
sudo systemctl restart "$RENDERER"
ready=0
for attempt in $(seq 1 20); do
    next_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
    if systemctl is-active --quiet "$RENDERER" && [[ "$next_pid" =~ ^[0-9]+$ && "$next_pid" -gt 1 && "$next_pid" != "$renderer_pid" ]]; then
        ready=1; break
    fi
    sleep 1
done
(( ready )) || fail 'Renderer não retomou após restart'
sleep 15
systemctl is-active --quiet "$RENDERER" || fail 'Renderer caiu após readiness'
[[ "$(systemctl show "$RENDERER" -p MainPID --value)" == "$next_pid" ]] || fail 'Renderer reiniciou inesperadamente'
[[ "$(systemctl show "$WORLD" -p MainPID --value)" == "$world_pid" ]] || fail 'Single Writer reiniciou'
[[ "$(systemctl show "$API" -p MainPID --value)" == "$api_pid" ]] || fail 'API reiniciou'
[[ "$(systemctl show "$AUDIO" -p MainPID --value)" == "$audio_pid" ]] || fail 'Áudio reiniciou'
trap - EXIT
applied=0
echo "MVP016_RENDER_DEPLOY_OK renderer_pid=$next_pid world_pid=$world_pid api_pid=$api_pid audio_pid=$audio_pid"
journalctl -u "$RENDERER" --since '60 seconds ago' --no-pager | grep -E 'CPU pressure: Godot FPS|pipeline:|started' | tail -12 || true
head -1 /proc/pressure/cpu
for attempt in 1 2 3; do
    if curl -fsS --max-time 8 http://127.0.0.1:8080/api/health > /dev/null; then
        echo 'API_HEALTH_OK'; break
    fi
    sleep 2
done
echo 'MVP016_RENDER_FINISHED'
