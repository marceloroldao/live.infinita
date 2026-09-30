#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
DATA=/var/lib/live-infinita/autonomous-world
SERVICE=live-infinita-autonomous-world.service
INDEX="$DATA/proposals.jsonl.index.sqlite3"
BACKUP="$(mktemp -d /tmp/live-infinita-008g.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-proposal-sidecar-index-008g.sh" >&2
  exit 1
fi

backup_one() {
  local target="$1"
  local rel="${target#/}"
  if [[ -e "$target" || -L "$target" ]]; then
    install -d "$BACKUP/$(dirname "$rel")"
    cp -a -- "$target" "$BACKUP/$rel"
  else
    printf '%s\n' "$target" >>"$ABSENT"
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
  "$INSTALL/apps/world-runtime/proposal_ledger_sidecar.py"
  "$INSTALL/apps/world-runtime/proposal_ledger_bridge.py"
  "$INSTALL/apps/world-runtime/autonomous_runtime.py"
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
echo "[008g] tick antes: $baseline_tick"

rollback() {
  local rc=$?
  trap - ERR
  set +e
  for target in "${TARGETS[@]}"; do
    restore_one "$target"
  done
  systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008g] rollback de código concluído. O sidecar derivado pode permanecer; o código anterior o ignora." >&2
  exit "$rc"
}
trap rollback ERR

test -s "$DATA/proposals.jsonl"
test -s "$DATA/plans.jsonl.index.sqlite3"

echo "[008g] Parando apenas o autonomous-world..."
systemctl stop "$SERVICE"
for _ in {1..60}; do
  if ! systemctl is-active --quiet "$SERVICE"; then
    break
  fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "[008g] autonomous-world não parou; abortando antes de construir o índice." >&2
  exit 1
fi

echo "[008g] Instalando índice lateral de propostas..."
for name in proposal_ledger.py proposal_ledger_sidecar.py proposal_ledger_bridge.py autonomous_runtime.py; do
  install -o liveinfinita -g liveinfinita -m 0644     "$REPO/apps/world-runtime/$name"     "$INSTALL/apps/world-runtime/$name"
done

source_bytes="$(stat -c %s "$DATA/proposals.jsonl")"
echo "[008g] proposals.jsonl autoritativo: $source_bytes bytes"

build_started="$(date +%s)"
runuser -u liveinfinita --   "$INSTALL/.venv/bin/python"   "$INSTALL/apps/world-runtime/proposal_ledger_sidecar.py"   "$DATA/proposals.jsonl" --rebuild
build_seconds="$(( $(date +%s) - build_started ))"

python3 - <<'PY'
import sqlite3
from pathlib import Path

root=Path("/var/lib/live-infinita/autonomous-world")
source=root/"proposals.jsonl"
index=root/"proposals.jsonl.index.sqlite3"
assert source.is_file() and source.stat().st_size > 0
assert index.is_file() and index.stat().st_size > 0

db=sqlite3.connect(f"file:{index}?mode=ro", uri=True)
try:
    meta=dict(db.execute("SELECT key,value FROM meta"))
    assert meta["schema"]=="live-infinita-proposal-ledger-index/v1"
    assert int(meta["indexed_size"])==source.stat().st_size
    proposals=int(db.execute("SELECT COUNT(*) FROM proposals").fetchone()[0])
    nonterminal=int(db.execute(
        "SELECT COUNT(*) FROM proposals WHERE status NOT IN ('committed','rejected','expired')"
    ).fetchone()[0])
    keys=int(db.execute(
        "SELECT COUNT(*) FROM proposals WHERE idempotency_key IS NOT NULL"
    ).fetchone()[0])
    sources=int(db.execute(
        "SELECT COUNT(*) FROM proposals WHERE source_proposal_id IS NOT NULL"
    ).fetchone()[0])
finally:
    db.close()
print(
    f"proposal_sidecar_ok proposals={proposals} nonterminal={nonterminal} "
    f"idempotency_keys={keys} source_links={sources} "
    f"index_bytes={index.stat().st_size}"
)
assert proposals > 0
PY

stat -c '[008g] index owner=%U:%G size=%s path=%n' "$INDEX"

echo "[008g] Reiniciando single writer..."
start_epoch="$(date +%s)"
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
startup_seconds="$(( $(date +%s) - start_epoch ))"

if (( advanced != 1 )); then
  echo "[008g] single writer não retomou avanço em até 60s." >&2
  systemctl show "$SERVICE" -p ActiveState -p SubState -p Result -p MainPID -p NRestarts --no-pager >&2 || true
  journalctl -u "$SERVICE" -n 100 --no-pager >&2 || true
  exit 1
fi

state="$(systemctl show "$SERVICE"   -p ActiveState -p SubState -p Result -p MainPID -p NRestarts -p Environment --no-pager)"
printf '%s\n' "$state"
grep -q 'ActiveState=active' <<<"$state"
grep -q 'SubState=running' <<<"$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER=1' <<<"$state"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008g-health.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008g-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

# Both acceleration indices must remain present.
test -s "$DATA/plans.jsonl.index.sqlite3"
test -s "$DATA/proposals.jsonl.index.sqlite3"

for name in proposal_ledger.py proposal_ledger_sidecar.py proposal_ledger_bridge.py autonomous_runtime.py; do
  repo_hash="$(sha256sum "$REPO/apps/world-runtime/$name" | cut -d' ' -f1)"
  installed_hash="$(sha256sum "$INSTALL/apps/world-runtime/$name" | cut -d' ' -f1)"
  [[ "$repo_hash" == "$installed_hash" ]]
done

echo "[008g] sidecar build: ${build_seconds}s"
echo "[008g] tick retomado: $baseline_tick -> $current_tick em ${startup_seconds}s"

trap - ERR
rm -rf -- "$BACKUP"
echo "[008g] OK: proposals.jsonl continua autoritativo; índice lateral persistente ativo."
