#!/usr/bin/env bash
set -Eeuo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON=/opt/live.infinita/.venv/bin/python
[ -x "$PYTHON" ] || PYTHON=python3
REPORT="/home/etbra/008cz-navigation-$(date -u +%Y%m%dT%H%M%SZ).json"
"$PYTHON" "$REPO/tools/audit_live_navigation_008cm.py" --latest-session --report "$REPORT" > "${REPORT%.json}.summary.json"
"$PYTHON" - "$REPORT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
a=r["all"]
print("Sessão:",r["selected_session_id"])
print("Passos concluídos:",a["completed_steps"])
print("Chegadas observadas:",a["goals_reached"])
print("Distância observada (m):",a["observed_distance_m"])
print("Colisões:",a["collisions"])
print("Passos concluídos com atalho:",a["completed_shortcut_steps"])
print("Ações causais RAM:",r["verified_causal_ram"]["actions"])
print("Ações causais Memoria.ia:",r["verified_causal_memoria"]["actions"])
for route in r["committed_routes"]["routes"]:
    q=route["path_quality"]
    print("Rota:",route["route_goal_id"],"restante (m):",q["last_observed_remaining_goal_m"],
        "passagens repetidas:",q["repeated_directed_passage_actions"])
print("Janela retida: não comprova o percurso completo nem ganho controlado na live.")
print("008CZ_AUDIT_OK report="+sys.argv[1])
PY
