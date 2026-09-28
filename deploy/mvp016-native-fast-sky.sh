#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
REQUIRED=bed38bf63be612430728e5c8cd1908b722d6678a
UNIT=live-infinita-renderer.service
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
fail(){ echo "MVP016C_FAST_SKY_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp016-native-fast-sky.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout contém alterações rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize a main antes de instalar'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'MVP-016C ainda não integrado à main'
for svc in "$UNIT" "$WORLD" "$API" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Broadcaster ativo: não trocar renderer durante transmissão'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
relay_pid="$(systemctl show "$RELAY" -p MainPID --value)"
renderer_pid="$(systemctl show "$UNIT" -p MainPID --value)"
echo "BEFORE world=$world_pid api=$api_pid audio=$audio_pid relay=$relay_pid renderer=$renderer_pid"

"$INSTALL/.venv/bin/python" -m unittest tests.test_native_sky_optimization tests.test_headless_renderer
bash -n "$REPO/deploy/mvp016-native-fast-sky.sh"
sudo -v
backup="/var/backups/live-infinita/mvp016c-native-sky-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
sudo cp -a "$INSTALL/apps/renderer-godot/main.gd" "$backup/main.gd"
sudo cp -a "/etc/systemd/system/$UNIT" "$backup/$UNIT"
original_shader=0
if [[ -f "$INSTALL/apps/renderer-godot/story_sky_native.gdshader" ]]; then
    original_shader=1
    sudo cp -a "$INSTALL/apps/renderer-godot/story_sky_native.gdshader" "$backup/story_sky_native.gdshader"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP016C_FAST_SKY_ROLLBACK: restaurando somente renderer' >&2
        sudo cp -a "$backup/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
        sudo cp -a "$backup/$UNIT" "/etc/systemd/system/$UNIT"
        if (( original_shader )); then
            sudo cp -a "$backup/story_sky_native.gdshader" "$INSTALL/apps/renderer-godot/story_sky_native.gdshader"
        else
            sudo rm -f "$INSTALL/apps/renderer-godot/story_sky_native.gdshader"
        fi
        sudo systemctl daemon-reload
        sudo systemctl restart "$UNIT" || true
    fi
}
trap rollback EXIT
applied=1
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/renderer-godot/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/renderer-godot/story_sky_native.gdshader" "$INSTALL/apps/renderer-godot/story_sky_native.gdshader"
sudo install -m 0644 "$REPO/deploy/$UNIT" "/etc/systemd/system/$UNIT"
cmp "$REPO/apps/renderer-godot/main.gd" "$INSTALL/apps/renderer-godot/main.gd"
cmp "$REPO/apps/renderer-godot/story_sky_native.gdshader" "$INSTALL/apps/renderer-godot/story_sky_native.gdshader"
cmp "$REPO/deploy/$UNIT" "/etc/systemd/system/$UNIT"
echo '== Reiniciando somente o renderer =='
started_at="$(date -u '+%Y-%m-%d %H:%M:%S')"
sudo systemctl daemon-reload
sudo systemctl restart "$UNIT"
ready=0
for attempt in $(seq 1 25); do
    next_pid="$(systemctl show "$UNIT" -p MainPID --value)"
    if systemctl is-active --quiet "$UNIT" && [[ "$next_pid" =~ ^[0-9]+$ && "$next_pid" -gt 1 && "$next_pid" != "$renderer_pid" ]] &&
       journalctl -u "$UNIT" --since "$started_at" --no-pager | grep -F '[render] native fast sky enabled' > /dev/null; then
        ready=1; break
    fi
    sleep 1
done
(( ready )) || fail 'Novo shader não iniciou no renderer'
sleep 10
systemctl is-active --quiet "$UNIT" || fail 'Renderer não permaneceu ativo'
[[ "$(systemctl show "$UNIT" -p MainPID --value)" == "$next_pid" ]] || fail 'Renderer reiniciou inesperadamente'
if journalctl -u "$UNIT" --since "$started_at" --no-pager | grep -Eq 'SCRIPT ERROR|Parser Error|Shader compilation failed'; then
    fail 'Godot reportou erro de script/shader'
fi
for row in "$WORLD:$world_pid" "$API:$api_pid" "$AUDIO:$audio_pid" "$RELAY:$relay_pid"; do
    IFS=: read -r svc expected <<< "$row"
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
    [[ "$(systemctl show "$svc" -p MainPID --value)" == "$expected" ]] || fail "$svc teve reinício inesperado"
done
trap - EXIT
applied=0
echo "MVP016C_FAST_SKY_DEPLOY_OK renderer_pid=$next_pid world_pid=$world_pid api_pid=$api_pid audio_pid=$audio_pid"
echo '== CPU pressure and current governor target =='
head -1 /proc/pressure/cpu
cat /var/lib/live-infinita/render-runtime-status.json
echo
echo 'MVP016C_FAST_SKY_FINISHED'
