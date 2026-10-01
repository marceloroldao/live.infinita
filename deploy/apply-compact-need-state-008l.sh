#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
DATA=/var/lib/live-infinita/autonomous-world
SERVICE=live-infinita-autonomous-world.service
STATE="$DATA/npc-need-state.json"
JOURNAL="$DATA/npc-need-state.outcomes.jsonl"
BACKUP="$(mktemp -d /tmp/live-infinita-008l.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-compact-need-state-008l.sh" >&2
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

TARGET_CODE="$INSTALL/apps/world-runtime/npc_need_dynamics.py"
backup_one "$TARGET_CODE"
backup_one "$STATE"
backup_one "$JOURNAL"

legacy_info="$(python3 - <<'PY'
import json, os
p="/var/lib/live-infinita/autonomous-world/npc-need-state.json"
d=json.load(open(p))
print(
    os.path.getsize(p),
    len(d.get("applied_outcomes", {})),
    int(d.get("last_tick", 0)),
)
PY
)"
read -r legacy_bytes legacy_outcomes legacy_tick <<<"$legacy_info"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
persistent_backup="$DATA/npc-need-state.json.pre-008l-$stamp.bak"
cp -a -- "$STATE" "$persistent_backup"
echo "[008l] backup legado preservado: $persistent_backup"
echo "[008l] estado legado: bytes=$legacy_bytes outcomes=$legacy_outcomes tick=$legacy_tick"

baseline_tick="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/live-infinita/autonomous-world/simulation-clock.json")
print(int(json.loads(p.read_text()).get("tick", 0)))
PY
)"
echo "[008l] simulation clock baseline: $baseline_tick"

rollback() {
  local rc=$?
  trap - ERR
  set +e
  systemctl stop "$SERVICE" >/dev/null 2>&1 || true
  restore_one "$TARGET_CODE"
  restore_one "$STATE"
  restore_one "$JOURNAL"
  systemctl start "$SERVICE" >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008l] rollback de código + estado concluído. Backup forense preservado." >&2
  exit "$rc"
}
trap rollback ERR

test -s "$STATE"
test -s "$DATA/plans.jsonl.index.sqlite3"
test -s "$DATA/proposals.jsonl.index.sqlite3"

echo "[008l] Parando apenas o autonomous-world..."
systemctl stop "$SERVICE"
for _ in {1..60}; do
  if ! systemctl is-active --quiet "$SERVICE"; then
    break
  fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "[008l] autonomous-world não parou." >&2
  exit 1
fi

install -o liveinfinita -g liveinfinita -m 0644   "$REPO/apps/world-runtime/npc_need_dynamics.py"   "$TARGET_CODE"

python3 -m py_compile "$TARGET_CODE"

echo "[008l] Reiniciando single writer; migração ocorre no bootstrap..."
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
  echo "[008l] single writer não retomou >=2 ticks." >&2
  journalctl -u "$SERVICE" -n 140 --no-pager >&2 || true
  exit 1
fi

python3 - <<'PY'
import json, os
from pathlib import Path

state=Path("/var/lib/live-infinita/autonomous-world/npc-need-state.json")
journal=Path("/var/lib/live-infinita/autonomous-world/npc-need-state.outcomes.jsonl")

d=json.loads(state.read_text(encoding="utf-8"))
assert d.get("schema") == "npc_need_state_v2", d.get("schema")
assert "applied_outcomes" not in d
rows=int(d.get("applied_outcome_rows", -1))
assert rows >= 0
assert journal.is_file() and not journal.is_symlink()

count=0
seen=set()
with journal.open("rb") as fh:
    for raw in fh:
        if not raw.strip():
            continue
        row=json.loads(raw)
        outcome_id=str(row.get("outcome_id") or "")
        assert outcome_id
        assert outcome_id not in seen
        seen.add(outcome_id)
        count += 1

assert count == rows, (count, rows)
print(
    "need_state_v2_ok",
    f"snapshot_bytes={state.stat().st_size}",
    f"journal_bytes={journal.stat().st_size}",
    f"outcomes={count}",
)
PY

new_bytes="$(stat -c %s "$STATE")"
if (( legacy_outcomes > 0 && new_bytes >= legacy_bytes )); then
  echo "[008l] snapshot não compactou: $legacy_bytes -> $new_bytes" >&2
  exit 1
fi

if (( legacy_outcomes > 0 )); then
  journal_rows="$(grep -cve '^[[:space:]]*$' "$JOURNAL")"
  if (( journal_rows < legacy_outcomes )); then
    echo "[008l] journal perdeu outcomes: $journal_rows < $legacy_outcomes" >&2
    exit 1
  fi
fi

state="$(systemctl show "$SERVICE"   -p ActiveState -p SubState -p Result -p MainPID -p NRestarts -p Environment --no-pager)"
printf '%s
' "$state"
grep -q 'ActiveState=active' <<<"$state"
grep -q 'SubState=running' <<<"$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER=1' <<<"$state"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008l-health.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008l-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

repo_hash="$(sha256sum "$REPO/apps/world-runtime/npc_need_dynamics.py" | cut -d' ' -f1)"
installed_hash="$(sha256sum "$TARGET_CODE" | cut -d' ' -f1)"
[[ "$repo_hash" == "$installed_hash" ]]

test -s "$DATA/plans.jsonl.index.sqlite3"
test -s "$DATA/proposals.jsonl.index.sqlite3"

echo "[008l] tick retomado: $baseline_tick -> $current_tick"
echo "[008l] snapshot: $legacy_bytes -> $new_bytes bytes"
echo "[008l] journal outcomes >= $legacy_outcomes"

trap - ERR
rm -rf -- "$BACKUP"
echo "[008l] OK: need-state hot snapshot compactado; outcome journal durável ativo."
