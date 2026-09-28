#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
REQUIRED_HEAD=0b3f4e6f39634e8d3c291d3be4eec4ccb4a45e07
SERVICE=live-infinita.service
WORLD_SERVICE=live-infinita-autonomous-world.service
BACKUP=/var/backups/live-infinita/health-bounded-$(date +%Y%m%d-%H%M%S)

fail() { echo "HEALTH_HOTFIX_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail "Execute como etbra, sem sudo no comando externo."
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail "Checkout fora da main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Checkout com alteracoes rastreadas"
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail "Main local e remota divergem"
git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD || fail "Hotfix nao integrado a main"
bash -n "$REPO/deploy/health-bounded-hotfix.sh"
echo "== Testes focalizados =="
/opt/live.infinita/.venv/bin/python -m unittest tests.test_health_bounded_shadow tests.test_mvp012b_contextual_shadow
echo "== Estado previo =="
systemctl is-active --quiet "$WORLD_SERVICE" || fail "Single Writer inativo"
world_pid_before="$(systemctl show "$WORLD_SERVICE" -p MainPID --value)"
[[ "$world_pid_before" =~ ^[0-9]+$ && "$world_pid_before" -gt 1 ]] || fail "PID autoritativo invalido"
sudo -v
echo "== Backup dos arquivos HTTP =="
sudo install -d -m 0700 "$BACKUP"
for name in cognitive_shadow.py main_cognitive_live.py; do
  sudo cp -a "/opt/live.infinita/apps/world-runtime/$name" "$BACKUP/$name"
done
echo "BACKUP=$BACKUP"
echo "== Hotfix somente na API; Single Writer nao sera reiniciado =="
for name in cognitive_shadow.py main_cognitive_live.py; do
  sudo install -m 0644 -o liveinfinita -g liveinfinita "$REPO/apps/world-runtime/$name" "/opt/live.infinita/apps/world-runtime/$name"
  cmp "$REPO/apps/world-runtime/$name" "/opt/live.infinita/apps/world-runtime/$name" || fail "Codigo divergente: $name"
done
sudo systemctl restart "$SERVICE"
echo "== Teste HTTP com janela declarada =="
good=0
for attempt in $(seq 1 6); do
  if curl -fsS --max-time 12 http://127.0.0.1:8080/api/health | python3 -c '
import json,sys
p=json.load(sys.stdin)
s=(p.get("cognitive_gym_v2") or {}).get("shadow_observer") or {}
assert p.get("ok") is True
assert s.get("metrics_scope")=="recent_window"
assert s.get("max_window_bytes")==262144
assert s.get("direct_world_write") is False
assert s.get("selection_authority") is False
print("HTTP_HEALTH_BOUNDED_OK", "recent_records="+str(s.get("records")))
'; then
    good=1; break
  fi
  sleep 2
done
((good == 1)) || fail "API nao respondeu ao health delimitado"
systemctl is-active --quiet "$SERVICE" || fail "API inativa"
systemctl is-active --quiet "$WORLD_SERVICE" || fail "Single Writer inativo"
world_pid_after="$(systemctl show "$WORLD_SERVICE" -p MainPID --value)"
[[ "$world_pid_after" == "$world_pid_before" ]] || fail "PID do Single Writer mudou inesperadamente"
echo "== Integridade do replay =="
PYTHONPATH=/opt/live.infinita:/opt/live.infinita/apps/world-runtime \
  /opt/live.infinita/.venv/bin/python /home/etbra/verify-live-replay-prefix.py
systemctl show "$SERVICE" -p ActiveState -p SubState -p NRestarts
echo "HEALTH_HOTFIX_VALIDADO"
