#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
DATA=/var/lib/live-infinita/autonomous-world
SERVICE=live-infinita-autonomous-world.service
BACKUP="$(mktemp -d /tmp/live-infinita-008n.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-proposal-clock-storage-profiling-008n.sh" >&2
  exit 1
fi

backup_one() {
  local target="$1"
  local rel="${target#/}"
  if [[ -e "$target" || -L "$target" ]]; then
    install -d "$BACKUP/$(dirname "$rel")"
    cp -a -- "$target" "$BACKUP/$rel"
  else
    printf '%s
' "$target" >>"$ABSENT"
  fi
}

restore_one() {
  local target="$1"
  local rel="${target#/}"
  if grep -Fxq -- "$target" "$ABSENT"; then
    rm -f -- "$target"
  elif [[ -e "$BACKUP/$rel" || -L "$BACKUP/$rel" ]]; then
    install -d "$(dirname "$target")"
    cp -a -- "$BACKUP/$rel" "$target"
  fi
}

TARGETS=(
  "$INSTALL/apps/world-runtime/proposal_ledger.py"
  "$INSTALL/apps/world-runtime/simulation_clock.py"
  "$INSTALL/apps/world-runtime/tick_driver_main.py"
)
for target in "${TARGETS[@]}"; do
  backup_one "$target"
done

baseline_tick="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/live-infinita/autonomous-world/simulation-clock.json")
print(int(json.loads(p.read_text()).get("tick", 0)))
PY
)"

rollback() {
  local rc=$?
  trap - ERR
  set +e
  for target in "${TARGETS[@]}"; do
    restore_one "$target"
  done
  systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008n] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

test -s "$DATA/world-tick-profile.json"
test -s "$DATA/plans.jsonl.index.sqlite3"
test -s "$DATA/proposals.jsonl.index.sqlite3"
test -s "$DATA/npc-need-state.json"
test -s "$DATA/npc-need-state.outcomes.jsonl"

echo "[008n] Parando apenas o autonomous-world..."
systemctl stop "$SERVICE"
for _ in {1..60}; do
  if ! systemctl is-active --quiet "$SERVICE"; then
    break
  fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "[008n] autonomous-world não parou." >&2
  exit 1
fi

for name in proposal_ledger.py simulation_clock.py tick_driver_main.py; do
  install -o liveinfinita -g liveinfinita -m 0644     "$REPO/apps/world-runtime/$name"     "$INSTALL/apps/world-runtime/$name"
done

python3 -m py_compile   "$INSTALL/apps/world-runtime/proposal_ledger.py"   "$INSTALL/apps/world-runtime/simulation_clock.py"   "$INSTALL/apps/world-runtime/tick_driver_main.py"

systemctl start "$SERVICE"

advanced=0
current_tick="$baseline_tick"
for _ in {1..60}; do
  if systemctl is-active --quiet "$SERVICE"; then
    current_tick="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/live-infinita/autonomous-world/simulation-clock.json")
print(int(json.loads(p.read_text()).get("tick", 0)))
PY
)"
    if (( current_tick >= baseline_tick + 2 )); then
      advanced=1
      break
    fi
  fi
  sleep 1
done

if (( advanced != 1 )); then
  echo "[008n] single writer não retomou >=2 ticks." >&2
  journalctl -u "$SERVICE" -n 120 --no-pager >&2 || true
  exit 1
fi

state="$(systemctl show "$SERVICE"   -p ActiveState -p SubState -p Result -p MainPID -p NRestarts -p Environment --no-pager)"
printf '%s
' "$state"
grep -q 'ActiveState=active' <<<"$state"
grep -q 'SubState=running' <<<"$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER=1' <<<"$state"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008n-health.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008n-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

for name in proposal_ledger.py simulation_clock.py tick_driver_main.py; do
  repo_hash="$(sha256sum "$REPO/apps/world-runtime/$name" | cut -d' ' -f1)"
  installed_hash="$(sha256sum "$INSTALL/apps/world-runtime/$name" | cut -d' ' -f1)"
  [[ "$repo_hash" == "$installed_hash" ]]
done

test -s "$DATA/plans.jsonl.index.sqlite3"
test -s "$DATA/proposals.jsonl.index.sqlite3"

echo "[008n] tick retomado: $baseline_tick -> $current_tick"
echo "[008n] spans: proposal.ledger.* + clock.storage.*"

trap - ERR
rm -rf -- "$BACKUP"
echo "[008n] OK: instrumentação observacional de ProposalLedger/SimulationClock instalada."
