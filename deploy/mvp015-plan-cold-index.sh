#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
REQUIRED_HEAD=85e1d53de94a9b97d3c79fe91d73d9a1db9bfafd
SERVICE=live-infinita-autonomous-world.service
MODULE=apps/world-runtime/plan_ledger.py
DATA=/var/lib/live-infinita/autonomous-world
fail(){ echo "MVP015_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra, sem sudo no comando externo.'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Alteracoes locais rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Main local e remota divergentes'
git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD || fail 'Codigo MVP-015 nao integrado na main'
[[ -f "$REPO/$MODULE" ]] || fail 'Modulo fonte ausente'
[[ -n "$(swapon --noheadings --show=NAME)" ]] || fail 'Swap nao ativo: execute ~/enable-live-swap-guard.sh primeiro'
systemctl is-active --quiet "$SERVICE" || fail 'Single Writer nao esta ativo'
pid_before="$(systemctl show "$SERVICE" -p MainPID --value)"
[[ "$pid_before" =~ ^[0-9]+$ && "$pid_before" -gt 1 ]] || fail 'PID anterior invalido'
rss_before="$(awk '/^VmRSS:/{print $2}' "/proc/$pid_before/status")"
tick_before="$(python3 -c 'import json;print(json.load(open("/var/lib/live-infinita/autonomous-world/simulation-clock.json"))["tick"])')"
echo "BEFORE pid=$pid_before rss_kb=$rss_before tick=$tick_before"
echo '== Testes =='
/opt/live.infinita/.venv/bin/python -m unittest tests.test_plan_ledger_cold_index tests.test_ledger_materialized_views tests.test_plan_ledger_crash_safety
sudo -v
echo '== Replay anterior =='
PYTHONPATH=/opt/live.infinita:/opt/live.infinita/apps/world-runtime \
  /opt/live.infinita/.venv/bin/python /home/etbra/verify-live-replay-prefix.py
echo '== Backup do modulo: sem modificar diários históricos =='
backup="/var/backups/live-infinita/mvp015-plan-cold-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
sudo cp -a "/opt/live.infinita/$MODULE" "$backup/plan_ledger.py"
sudo cp -a "$DATA/simulation-clock.json" "$backup/simulation-clock.json.predeploy"
echo "BACKUP=$backup"
echo '== Atualização cirúrgica do Single Writer =='
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$MODULE" "/opt/live.infinita/$MODULE"
cmp "$REPO/$MODULE" "/opt/live.infinita/$MODULE" || fail 'Arquivo divergente'
sudo systemctl restart "$SERVICE"
pid_after="$(systemctl show "$SERVICE" -p MainPID --value)"
[[ "$pid_after" =~ ^[0-9]+$ && "$pid_after" -gt 1 && "$pid_after" != "$pid_before" ]] || fail 'PID nao renovado'
echo "AFTER_PID=$pid_after"
echo '== Checagem de retomada e RSS =='
resumed=0
for attempt in $(seq 1 120); do
  systemctl is-active --quiet "$SERVICE" || fail 'Single Writer caiu'
  current_pid="$(systemctl show "$SERVICE" -p MainPID --value)"
  [[ "$current_pid" == "$pid_after" ]] || fail 'Single Writer reiniciou inesperadamente'
  tick_after="$(python3 -c 'import json;print(json.load(open("/var/lib/live-infinita/autonomous-world/simulation-clock.json"))["tick"])' 2>/dev/null || echo 0)"
  if [[ "$tick_after" =~ ^[0-9]+$ ]] && ((tick_after >= tick_before + 2)); then resumed=1; break; fi
  sleep 2
done
((resumed == 1)) || fail 'Relogio nao avancou após restart'
rss_after="$(awk '/^VmRSS:/{print $2}' "/proc/$pid_after/status")"
echo "RSS_BEFORE_KB=$rss_before RSS_AFTER_KB=$rss_after"
echo "TICK_BEFORE=$tick_before TICK_AFTER=$tick_after"
if ((rss_after * 100 >= rss_before * 80)); then
  echo "WARNING: RSS did not decrease by 20 percent. Investigate further."
  fail 'Reducao de memoria ainda nao demonstrada'
fi
echo '== HTTP =='
curl -fsS --max-time 12 http://127.0.0.1:8080/api/health | python3 -c 'import json,sys;d=json.load(sys.stdin);s=(d.get("cognitive_gym_v2") or {}).get("shadow_observer") or {};assert d.get("ok") is True;assert s.get("metrics_scope")=="recent_window";assert s.get("direct_world_write") is False and s.get("selection_authority") is False; print("HEALTH_OK bounded shadow")'
echo '== Social gate =='
python3 "$REPO/deploy/verify-mvp014b-social.py" "$DATA"
echo '== Replay =='
PYTHONPATH=/opt/live.infinita:/opt/live.infinita/apps/world-runtime \
  /opt/live.infinita/.venv/bin/python /home/etbra/verify-live-replay-prefix.py
systemctl show "$SERVICE" -p ActiveState -p MainPID -p NRestarts -p ExecMainStatus
echo 'MVP015_PLAN_COLD_INDEX_VALIDADO'
