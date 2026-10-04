#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
SRC="$REPO/apps/world-runtime"
DST="$INSTALL/apps/world-runtime"
SERVICE=live-infinita-autonomous-world.service
PYTHON="$INSTALL/.venv/bin/python"
cd "$REPO"
test -z "$(git status --porcelain)"
SHA="$(git rev-parse HEAD)"
FILES=(npc_environmental_exploration.py npc_idle_wander.py npc_cognitive_stack.py autonomous_runtime.py world_tick.py)
# Confirm the reviewed source and reject unrelated installed changes.
for f in "${FILES[@]}"; do
  git cat-file -e "$SHA:apps/world-runtime/$f"
  if [ "$f" != npc_environmental_exploration.py ]; then
    cmp <(git show "$SHA^:apps/world-runtime/$f") "$DST/$f"
  fi
done
PYTHONDONTWRITEBYTECODE=1 "$PYTHON" - <<'PY'
import sys,unittest
patterns = ["test_environmental_exploration_008by.py", "test_nov_exploration_007.py",
            "test_nov_autonomous_scenario.py", "test_environmental_rules_008be.py",
            "test_agent_intent_protocol.py", "test_world_tick*.py", "test_npc_idle*.py",
            "test_npc_cognitive_stack*.py", "test_autonomous_runtime*.py", "test_idle*.py",
            "test_plan_scheduler*.py", "test_npc_need_scheduler*.py"]
loader=unittest.TestLoader()
suite=unittest.TestSuite(loader.discover("tests",pattern=p) for p in patterns)
result=unittest.TextTestRunner(verbosity=1).run(suite)
sys.exit(not result.wasSuccessful())
PY
BACKUP="$INSTALL/.rollouts/008by-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
for f in "${FILES[@]}"; do
  if [ -f "$DST/$f" ]; then cp -a "$DST/$f" "$BACKUP/$f"; fi
done
rollback() {
  rc=$?
  trap - ERR
  echo "ROLLBACK 008BY rc=$rc" >&2
  for f in "${FILES[@]}"; do
    if [ -f "$BACKUP/$f" ]; then
      install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$f" "$DST/$f"
    elif [ "$f" = npc_environmental_exploration.py ]; then
      rm -f "$DST/$f"
    fi
  done
  systemctl restart "$SERVICE" || true
  exit "$rc"
}
trap rollback ERR
for f in "${FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$SRC/$f" "$DST/$f"
done
PYTHONPATH="$INSTALL:$DST" "$PYTHON" - <<'PY'
import json
from pathlib import Path
from npc_environmental_exploration import EnvironmentalExploration, choose_local_region
world_file=Path("/var/lib/live-infinita/autonomous-world/world.json")
provider=EnvironmentalExploration(lambda: json.loads(world_file.read_text()),
    Path("/var/lib/live-infinita/cognitive-terrain/projection.json"))
value=provider()
assert value.get("state_id") and value.get("regions"), "Environmental stimulus unavailable"
print("008BY_ENVIRONMENT_OK",value["state_id"],len(value["regions"]))
PY
BEFORE="$("$PYTHON" -c 'import json; print(json.load(open("/var/lib/live-infinita/autonomous-world/simulation-clock.json"))["tick"])')"
systemctl restart "$SERVICE"
sleep 8
systemctl is-active --quiet "$SERVICE"
"$PYTHON" - "$BEFORE" <<'PY'
import json,sys,urllib.request
tick=json.load(open("/var/lib/live-infinita/autonomous-world/simulation-clock.json"))["tick"]
assert tick > int(sys.argv[1]), "Simulation clock did not advance"
with urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=10) as r:
    assert json.load(r)["ok"] is True
print("008BY_RUNTIME_OK tick",tick)
PY
trap - ERR
echo "008BY_OK source=$SHA backup=$BACKUP"
