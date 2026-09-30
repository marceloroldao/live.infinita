#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
DATA=/var/lib/live-infinita/autonomous-world
SERVICE=live-infinita-autonomous-world.service
BACKUP="$(mktemp -d /tmp/live-infinita-008d.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-hot-ledger-008d.sh" >&2
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
  "$INSTALL/apps/world-runtime/conditional_event_scheduler.py"
  "$INSTALL/apps/world-runtime/plan_ledger.py"
  "$INSTALL/apps/world-runtime/proposal_ledger.py"
  "$INSTALL/apps/world-runtime/hot_ledger_compactor.py"
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
echo "[008d] tick antes da manutenção: $baseline_tick"

rollback() {
  local rc=$?
  trap - ERR
  set +e
  for target in "${TARGETS[@]}"; do
    restore_one "$target"
  done
  systemctl daemon-reload
  systemctl restart "$SERVICE" >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008d] rollback de código concluído. Arquivos históricos compactados permanecem preservados nos .archive-*." >&2
  exit "$rc"
}
trap rollback ERR

echo "[008d] Parando apenas o autonomous-world single writer..."
systemctl stop "$SERVICE"
for _ in {1..60}; do
  if ! systemctl is-active --quiet "$SERVICE"; then
    break
  fi
  sleep 1
done
if systemctl is-active --quiet "$SERVICE"; then
  echo "[008d] autonomous-world não parou com segurança; abortando antes de tocar nos ledgers." >&2
  exit 1
fi

echo "[008d] Instalando hot-state ledgers..."
for name in conditional_event_scheduler.py plan_ledger.py proposal_ledger.py hot_ledger_compactor.py; do
  install -o liveinfinita -g liveinfinita -m 0644     "$REPO/apps/world-runtime/$name"     "$INSTALL/apps/world-runtime/$name"
done

echo "[008d] Tamanhos antes:"
du -h   "$DATA/conditional-world-events.jsonl"   "$DATA/plans.jsonl"   "$DATA/proposals.jsonl"

echo "[008d] Compactando sem apagar histórico..."
"$INSTALL/.venv/bin/python"   "$INSTALL/apps/world-runtime/hot_ledger_compactor.py"   --conditional "$DATA/conditional-world-events.jsonl"   --plans "$DATA/plans.jsonl"   --proposals "$DATA/proposals.jsonl"

python3 - <<'PY'
import json
from pathlib import Path
root=Path("/var/lib/live-infinita/autonomous-world")
for name,kind in (
    ("conditional-world-events.jsonl","conditional"),
    ("plans.jsonl","plans"),
    ("proposals.jsonl","proposals"),
):
    manifest=root/(name+".compaction.json")
    value=json.loads(manifest.read_text())
    assert value["schema"]=="live-infinita-hot-ledger-compaction/v1"
    assert value["kind"]==kind
    assert value["history_deleted"] is False
    archive=root/value["archive"]
    assert archive.is_file()
    active=root/name
    assert active.is_file() and active.stat().st_size > 0
    assert active.stat().st_size == int(value["compact_bytes"])
    print(
        f"{kind}: {value['original_rows']} -> {value['latest_rows']} rows; "
        f"{value['original_bytes']} -> {value['compact_bytes']} bytes; "
        f"archive={archive.name}"
    )
PY

echo "[008d] Tamanhos quentes depois:"
du -h   "$DATA/conditional-world-events.jsonl"   "$DATA/plans.jsonl"   "$DATA/proposals.jsonl"

echo "[008d] Reiniciando single writer..."
systemctl start "$SERVICE"

advanced=0
current_tick="$baseline_tick"
for _ in {1..120}; do
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
  echo "[008d] single writer não retomou avanço lógico após compactação." >&2
  systemctl show "$SERVICE" -p ActiveState -p SubState -p Result -p MainPID -p NRestarts --no-pager >&2 || true
  journalctl -u "$SERVICE" -n 80 --no-pager >&2 || true
  exit 1
fi

state="$(systemctl show "$SERVICE"   -p ActiveState -p SubState -p Result -p MainPID -p NRestarts -p Environment --no-pager)"
printf '%s\n' "$state"
grep -q 'ActiveState=active' <<<"$state"
grep -q 'SubState=running' <<<"$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER=1' <<<"$state"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008d-health.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008d-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

echo "[008d] tick retomado: $baseline_tick -> $current_tick"
echo "[008d] últimos eventos do construtor:"
grep 'cognitive_world_builder' "$DATA/events.jsonl" | tail -n 5 || true

trap - ERR
rm -rf -- "$BACKUP"
echo "[008d] OK: histórico arquivado, hot state compacto e autonomous-world avançando."
