#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
REQUIRED=72c3499489cc68486483c365ff04f1d74255b08b
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
RENDERER=live-infinita-renderer.service
fail(){ echo "MVP016_METRICS_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp016-performance-metrics.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout com alterações locais rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize main antes do deploy'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'Correção MVP-016B ainda não integrada'
for svc in "$WORLD" "$API" "$AUDIO" "$RENDERER"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Broadcaster em transmissão: não reiniciar API/renderer durante LIVE'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
echo "BEFORE world=$world_pid audio=$audio_pid api=$api_pid renderer=$renderer_pid"
echo '== Testes = background-only changes =='
PYTHONPATH=.:apps/world-runtime:apps/audio-service:apps/audience "$INSTALL/.venv/bin/python" -m unittest tests.test_manager_performance tests.test_headless_renderer
bash -n "$REPO/deploy/mvp016-performance-metrics.sh"
sudo -v
backup="/var/backups/live-infinita/mvp016-metrics-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
for file in apps/headless-renderer/headless_renderer.py apps/world-runtime/main_cognitive_live.py apps/world-runtime/main_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css; do
    sudo cp -a "$INSTALL/$file" "$backup/$(basename "$file")"
done
if [[ -e "$INSTALL/packages/observability/runtime_metrics.py" ]]; then
    sudo cp -a "$INSTALL/packages/observability/runtime_metrics.py" "$backup/runtime_metrics.py"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP016_METRICS_ROLLBACK: código de API/renderer/manager apenas' >&2
        for file in apps/headless-renderer/headless_renderer.py apps/world-runtime/main_cognitive_live.py apps/world-runtime/main_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css; do
            sudo cp -a "$backup/$(basename "$file")" "$INSTALL/$file"
        done
        if [[ -f "$backup/runtime_metrics.py" ]]; then
            sudo cp -a "$backup/runtime_metrics.py" "$INSTALL/packages/observability/runtime_metrics.py"
        else
            sudo rm -f "$INSTALL/packages/observability/runtime_metrics.py"
        fi
        sudo systemctl restart "$API" "$RENDERER" || true
    fi
}
trap rollback EXIT
applied=1
for file in apps/headless-renderer/headless_renderer.py apps/world-runtime/main_cognitive_live.py apps/world-runtime/main_live.py apps/manager/index.html apps/manager/app.js apps/manager/monitoring.css packages/observability/runtime_metrics.py; do
    sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$file" "$INSTALL/$file"
    cmp "$REPO/$file" "$INSTALL/$file"
done
sudo "$INSTALL/.venv/bin/python" -m py_compile "$INSTALL/apps/headless-renderer/headless_renderer.py" "$INSTALL/apps/world-runtime/main_cognitive_live.py" "$INSTALL/apps/world-runtime/main_live.py" "$INSTALL/packages/observability/runtime_metrics.py"
(cd /tmp && sudo -u liveinfinita "$INSTALL/.venv/bin/python" -c "import sys; sys.path.insert(0, '$INSTALL'); from packages.observability.runtime_metrics import runtime_snapshot; print('MVP016_MODULE_IMPORT_OK')")
if command -v node >/dev/null 2>&1; then
    node --check "$INSTALL/apps/manager/app.js"
fi
sudo systemctl restart "$API" "$RENDERER"
ready=0
for attempt in $(seq 1 16); do
    if systemctl is-active --quiet "$API" && systemctl is-active --quiet "$RENDERER" &&
       curl -fsS --max-time 8 -o /dev/null http://127.0.0.1:8080/api/health 2>/dev/null; then
        ready=1; break
    fi
    sleep 2
done
(( ready )) || fail 'API ou renderer não retomou'
sleep 12
systemctl is-active --quiet "$API" || fail 'API caiu após readiness'
systemctl is-active --quiet "$RENDERER" || fail 'Renderer caiu após readiness'
[[ "$(systemctl show "$WORLD" -p MainPID --value)" == "$world_pid" ]] || fail 'Single Writer alterou PID'
[[ "$(systemctl show "$AUDIO" -p MainPID --value)" == "$audio_pid" ]] || fail 'Áudio alterou PID'
[[ "$(systemctl show "$API" -p MainPID --value)" != "$api_pid" ]] || fail 'API não reiniciou'
[[ "$(systemctl show "$RENDERER" -p MainPID --value)" != "$renderer_pid" ]] || fail 'Renderer não reiniciou'
sudo "$INSTALL/.venv/bin/python" - <<'PY'
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
env = Path("/etc/live-infinita/operator.env").read_text()
token = next((line.partition("=")[2].strip() for line in env.splitlines()
              if line.startswith("LIVE_INFINITA_OPERATOR_TOKEN=")), "")
assert token, "operator token absent"
url = "http://127.0.0.1:8080/api/manage/performance"
for attempt in range(4):
    try:
        with urlopen(Request(url, headers={"Authorization": "Bearer " + token}), timeout=12) as reply:
            metrics = json.load(reply)
        assert all(k in metrics for k in ("host", "api", "renderer", "audio", "audio_web"))
        assert metrics["renderer"]["available"], "renderer telemetry missing/stale"
        assert metrics["host"]["cpu_pressure_avg10_pct"] is not None
        print("MVP016_METRICS_ENDPOINT_OK",
              "cpu_pressure=", metrics["host"]["cpu_pressure_avg10_pct"],
              "godot_fps=", metrics["renderer"]["fps"],
              "capture_fps=", metrics["renderer"]["capture_fps"],
              "voice_chunks=", metrics["audio"]["voice_chunks"],
              "audio_web=", metrics["audio_web"]["available"])
        break
    except Exception as exc:
        if attempt == 3:
            raise
        time.sleep(2)
PY
trap - EXIT
applied=0
echo "MVP016_METRICS_DEPLOY_OK world_pid=$world_pid audio_pid=$audio_pid"
echo 'MVP016_METRICS_FINISHED'
