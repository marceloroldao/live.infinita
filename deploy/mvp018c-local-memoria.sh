#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
VENDOR=/opt/live-infinita-memoria-rc2
LAB=/home/etbra/live-infinita-lab/memoria.ia-rc2
DATA=/var/lib/live-infinita/memoria-local
PIN=e38f27b639bec1cfcb83694c1418a4d01f250ffd
REQUIRED=22edd682d93e62cd263855eec6ff257636096c44
WORKER=live-infinita-local-memoria.service
TIMER=live-infinita-local-memoria.timer
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
RENDERER=live-infinita-renderer.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service

fail(){ echo "MVP018C_LOCAL_MEMORIA_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail "Execute como etbra: bash deploy/mvp018c-local-memoria.sh"
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail "Checkout fora da main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Checkout contém alterações rastreadas"
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail "Atualize a main antes da instalação"
git merge-base --is-ancestor "$REQUIRED" HEAD || fail "MVP-018C não foi integrado ao main"

for svc in "$WORLD" "$API" "$RENDERER" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "$svc está inativo"
done
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
relay_pid="$(systemctl show "$RELAY" -p MainPID --value)"
echo "BEFORE world=$world_pid api=$api_pid renderer=$renderer_pid audio=$audio_pid relay=$relay_pid"

if [[ ! -d "$LAB/.git" ]]; then
    mkdir -p "$(dirname "$LAB")"
    git clone --filter=blob:none --depth 1 --branch v2.0.0-rc2 \
        https://github.com/marceloroldao/memoria.ia.git "$LAB"
fi
[[ "$(git -C "$LAB" rev-parse HEAD)" == "$PIN" ]] || fail "Fonte Memoria.ia local não corresponde à RC2 publicada"
[[ -z "$(git -C "$LAB" status --porcelain --untracked-files=no)" ]] || fail "Fonte Memoria.ia foi modificada"
test -f "$LAB/src/memoria_resolutiva/product_evidence.py" || fail "EvidenceCore indisponível no pin"
echo "MEMORIA_LOCAL_SOURCE_VERIFIED pin=$PIN"

bash -n "$REPO/deploy/mvp018c-local-memoria.sh"
PYTHONPATH="$LAB/src:$REPO:$REPO/apps/world-runtime:$REPO/apps/audio-service:$REPO/apps/audience" \
    "$INSTALL/.venv/bin/python" -m unittest \
    tests.test_local_memoria_rc2 tests.test_nov_episode_sync_preview tests.test_nov_life_observability
sudo -v

backup="/var/backups/live-infinita/mvp018c-local-memoria-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
local_worker=apps/world-runtime/local_memoria_worker.py
had_worker=0
had_unit=0
had_timer=0
had_vendor=0
[[ -e "$INSTALL/$local_worker" ]] && had_worker=1 && sudo cp -a "$INSTALL/$local_worker" "$backup/local_memoria_worker.py"
[[ -e "/etc/systemd/system/$WORKER" ]] && had_unit=1 && sudo cp -a "/etc/systemd/system/$WORKER" "$backup/$WORKER"
[[ -e "/etc/systemd/system/$TIMER" ]] && had_timer=1 && sudo cp -a "/etc/systemd/system/$TIMER" "$backup/$TIMER"
if [[ -d "$VENDOR" ]]; then
    had_vendor=1
    [[ "$(cat "$VENDOR/commit.txt" 2>/dev/null)" == "$PIN" ]] || fail "Versão de Memoria.ia já instalada difere da RC2"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo "MVP018C_LOCAL_MEMORIA_ROLLBACK: units e worker; dados locais preservados" >&2
        sudo systemctl disable --now "$TIMER" >/dev/null 2>&1 || true
        if (( had_worker )); then sudo cp -a "$backup/local_memoria_worker.py" "$INSTALL/$local_worker"
        else sudo rm -f "$INSTALL/$local_worker"; fi
        if (( had_unit )); then sudo cp -a "$backup/$WORKER" "/etc/systemd/system/$WORKER"
        else sudo rm -f "/etc/systemd/system/$WORKER"; fi
        if (( had_timer )); then sudo cp -a "$backup/$TIMER" "/etc/systemd/system/$TIMER"
        else sudo rm -f "/etc/systemd/system/$TIMER"; fi
        if (( !had_vendor )); then sudo rm -rf "$VENDOR"; fi
        sudo systemctl daemon-reload || true
        if (( had_timer )); then sudo systemctl enable --now "$TIMER" >/dev/null 2>&1 || true; fi
    fi
}
trap rollback EXIT
applied=1

if (( !had_vendor )); then
    sudo install -d -m 0755 "$VENDOR/src"
    sudo cp -a "$LAB/src/memoria_resolutiva" "$VENDOR/src/memoria_resolutiva"
    printf '%s\n' "$PIN" | sudo tee "$VENDOR/commit.txt" >/dev/null
    sudo chmod -R a+rX "$VENDOR/src"
fi
[[ "$(cat "$VENDOR/commit.txt")" == "$PIN" ]] || fail "Instalação RC2 divergente"
sudo install -d -o liveinfinita -g liveinfinita -m 0700 "$DATA"
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$local_worker" "$INSTALL/$local_worker"
sudo install -m 0644 "$REPO/deploy/$WORKER" "/etc/systemd/system/$WORKER"
sudo install -m 0644 "$REPO/deploy/$TIMER" "/etc/systemd/system/$TIMER"
cmp "$REPO/$local_worker" "$INSTALL/$local_worker"
cmp "$REPO/deploy/$WORKER" "/etc/systemd/system/$WORKER"
cmp "$REPO/deploy/$TIMER" "/etc/systemd/system/$TIMER"

sudo systemctl daemon-reload
# A single bounded batch verifies the actual local EvidenceCore, SQLite and
# durable checkpoint. No API/World/renderer/audio service is restarted.
sudo systemctl start "$WORKER"
[[ "$(systemctl show "$WORKER" -p Result --value)" == success ]] ||
    fail "Worker não concluiu com sucesso"
[[ "$(systemctl show "$WORKER" -p ExecMainStatus --value)" == 0 ]] ||
    fail "Worker retornou status diferente de zero"
sudo -u liveinfinita env PYTHONPATH="$VENDOR/src:$INSTALL" \
    "$INSTALL/.venv/bin/python" "$INSTALL/$local_worker" --status
test -s "$DATA/memoria-local.sqlite3" || fail "Memória local SQLite não foi gravada"
sudo systemctl enable --now "$TIMER" >/dev/null
systemctl is-active --quiet "$TIMER" || fail "Timer local não está ativo"
[[ "$(systemctl is-enabled "$TIMER")" == enabled ]] || fail "Timer local não foi habilitado"
for row in "$WORLD:$world_pid" "$API:$api_pid" "$RENDERER:$renderer_pid" "$AUDIO:$audio_pid" "$RELAY:$relay_pid"; do
    IFS=: read -r svc expected <<< "$row"
    systemctl is-active --quiet "$svc" || fail "$svc deixou de funcionar"
    [[ "$(systemctl show "$svc" -p MainPID --value)" == "$expected" ]] ||
        fail "$svc reiniciou durante instalação da memória local"
done
trap - EXIT
applied=0
echo "MVP018C_LOCAL_MEMORIA_DEPLOY_OK world_pid=$world_pid"
echo "MVP018C_LOCAL_MEMORIA_FINISHED: offline RC2, SQLite, timer 2min, no central sync"
