#!/usr/bin/env bash
set -Eeuo pipefail

REPO="/home/etbra/live.infinita"
# The approved PR head must be part of main, even if main receives later commits.
REQUIRED_HEAD="ff926a47e8eefe282266ede6e57afc7c26aaa261"
DATA="/var/lib/live-infinita/autonomous-world"
SERVICE="live-infinita-autonomous-world.service"
SHADOW="$DATA/memoria-v2-shadow.jsonl"

fail(){ printf '[FAIL] %s\n' "$*" >&2; exit 2; }
if (( EUID == 0 )); then fail 'Execute como etbra, sem sudo no comando externo.'; fi

cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Alteracoes locais rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Main local/remota divergentes'
git merge-base --is-ancestor "$REQUIRED_HEAD" HEAD || fail 'MVP-014a ainda nao integrado a main'
[[ -f "$REPO/apps/world-runtime/npc_social_evidence.py" ]] || fail 'Modulo nao encontrado'

echo '== Suite completa de fonte aprovada =='
/opt/live.infinita/.venv/bin/python -m unittest discover -s tests -p 'test_*.py'
git diff --check
sudo -v
systemctl is-active --quiet "$SERVICE" || fail 'Servico nao esta ativo antes do deploy'

echo '== Preflight replay =='
PYTHONPATH=/opt/live.infinita:/opt/live.infinita/apps/world-runtime \
  /opt/live.infinita/.venv/bin/python /home/etbra/verify-live-replay-prefix.py

echo '== Backup ='
backup="/var/backups/live-infinita/mvp014a-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
sudo cp -a /etc/live-infinita/autonomous-world.env "$backup/"
sudo cp -a /etc/live-infinita/world-tick-profiler.env "$backup/"
sudo cp -a "$DATA/world.json" "$backup/world.json"
for f in npc_cognitive_stack.py world_tick.py cognitive_shadow.py shadow_world_tick.py; do
  sudo cp -a "/opt/live.infinita/apps/world-runtime/$f" "$backup/$f"
done
if [[ -f "$DATA/npc-social-evidence.jsonl" ]]; then
  sudo cp -a "$DATA/npc-social-evidence.jsonl" "$backup/npc-social-evidence.jsonl"
fi
echo "BACKUP=$backup"

echo '== Deploy principal =='
bash "$REPO/deploy/update.sh"

echo '== Modulos instalados =='
for f in npc_social_evidence.py npc_cognitive_stack.py world_tick.py cognitive_shadow.py shadow_world_tick.py; do
  cmp "$REPO/apps/world-runtime/$f" "/opt/live.infinita/apps/world-runtime/$f" || fail "Modulo divergente: $f"
done
systemctl is-active --quiet "$SERVICE" || fail 'Servico nao esta ativo apos deploy'
pid="$(systemctl show "$SERVICE" -p MainPID --value)"
[[ "$pid" =~ ^[0-9]+$ && "$pid" -gt 1 ]] || fail 'PID invalido'
flag="$(sudo cat "/proc/$pid/environ" | python3 -c 'import sys; print(next((v.decode(errors="replace") for v in sys.stdin.buffer.read().split(bytes([0])) if v.startswith(b"LIVE_INFINITA_MEMORIA_V2_SHADOW=")), "missing"))')"
echo "Shadow efetivo: $flag"
[[ "$flag" == "LIVE_INFINITA_MEMORIA_V2_SHADOW=1" ]] || fail 'Shadow desligado'
systemctl show "$SERVICE" -p ActiveState -p SubState -p NRestarts -p ExecMainStatus

echo '== Gate do novo contrato observacional =='
verified=0
for i in $(seq 1 90); do
  if python3 "$REPO/deploy/verify-mvp014a-social.py" "$DATA"; then
    verified=1
    break
  fi
  sleep 1
done
(( verified == 1 )) || fail 'Novo contrato de evidencia social nao observado'

echo '== Health =='
curl -fsS --max-time 120 http://127.0.0.1:8080/api/health | python3 -c '
import json,sys
d=json.load(sys.stdin)
c=d.get("cognitive_gym_v2") or {}
s=c.get("shadow_observer") or {}
assert d.get("ok") is True
assert c.get("enabled") is False and c.get("direct_world_write") is False
assert s.get("direct_world_write") is False and s.get("selection_authority") is False
print("HEALTH_OK contextual:",s.get("contextual_forecasts"),"paired:",s.get("paired_evaluated"))
'
echo '== Replay apos deploy =='
PYTHONPATH=/opt/live.infinita:/opt/live.infinita/apps/world-runtime \
  /opt/live.infinita/.venv/bin/python /home/etbra/verify-live-replay-prefix.py
echo 'MVP014A_DEPLOY_VALIDADO'
