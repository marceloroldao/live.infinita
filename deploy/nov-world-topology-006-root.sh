#!/usr/bin/env bash
set -Eeuo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE=/etc/live-infinita/autonomous-world.env
PROD_ROOT=/opt/live.infinita
PROD_RUNTIME="$PROD_ROOT/apps/world-runtime"
MIGRATION="$SOURCE_DIR/deploy/nov_world_topology_006.py"
TOPOLOGY="$SOURCE_DIR/examples/nov-world-regions-005.json"
TMP="$(mktemp -d /tmp/live-nov-topology-006.XXXXXX)"
MIGRATED=0
CODE_DEPLOYED=0
WRITERS_PAUSED=0

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/nov-world-topology-006-root.sh" >&2
  exit 1
fi
[[ -f "$ENV_FILE" ]] || { echo "Environment file ausente: $ENV_FILE" >&2; exit 2; }

set -a
source "$ENV_FILE"
set +a

: "${LIVE_INFINITA_DATA_DIR:?}"
: "${LIVE_INFINITA_COLD_STORE_DIR:?}"
: "${LIVE_INFINITA_COLD_BOOTSTRAP_FILE:?}"
LOCK="$LIVE_INFINITA_DATA_DIR/world-mutation.lock"
PY="$PROD_ROOT/.venv/bin/python"

mkdir -p "$TMP/code"
cp -a "$PROD_RUNTIME/cold_engine.py" "$TMP/code/cold_engine.py"
cp -a "$PROD_RUNTIME/autonomous_runtime.py" "$TMP/code/autonomous_runtime.py"

snapshot() {
  local name="$1"
  local out="$TMP/$name"
  mkdir -p "$out/data" "$out/cold"
  exec 9>>"$LOCK"
  flock -x 9
  cp "$LIVE_INFINITA_DATA_DIR/world.json" "$out/data/world.json"
  cp "$LIVE_INFINITA_DATA_DIR/deltas.jsonl" "$out/data/deltas.jsonl"
  cp "$LIVE_INFINITA_COLD_STORE_DIR/manifest.json" "$out/cold/manifest.json"
  flock -u 9
  exec 9>&-
  : >"$out/data/events.jsonl"
  echo "$out"
}
verify_snapshot() {
  local snap="$1"
  PYTHONPATH="$SOURCE_DIR:$SOURCE_DIR/apps/world-runtime" "$PY" - "$snap" "$LIVE_INFINITA_COLD_BOOTSTRAP_FILE" <<'PY'
from pathlib import Path
import sys
from cold_engine import ColdAuthoritativeWorldEngine
from packages.spatial import FileRegionColdStore
root=Path(sys.argv[1])
bootstrap=Path(sys.argv[2])
engine=ColdAuthoritativeWorldEngine(bootstrap, root/"data", FileRegionColdStore(root/"cold"))
result=engine.verify_replay()
print(result)
if not result.get("ok"):
    raise SystemExit(1)
PY
}

write_old_topology() {
  local snap="$1"
  "$PY" - "$snap/data/world.json" "$TMP/old-topology.json" <<'PY'
import json,sys
world=json.load(open(sys.argv[1],encoding="utf-8"))
json.dump(
    {"schema":"live-infinita-region-topology/rollback-v1","regions":world["regions"]},
    open(sys.argv[2],"w",encoding="utf-8"),
    ensure_ascii=False, indent=2, sort_keys=True,
)
PY
}

restore_topology() {
  [[ -f "$TMP/old-topology.json" ]] || return 0
  echo "[topology-006] Restaurando topologia anterior por delta canônico." >&2
  PYTHONPATH="$SOURCE_DIR:$SOURCE_DIR/apps/world-runtime" "$PY" "$MIGRATION"     --apply --replace-exact     --source deploy-nov-topology-006-rollback     --topology-file "$TMP/old-topology.json"     --bootstrap-file "$LIVE_INFINITA_COLD_BOOTSTRAP_FILE"     --data-dir "$LIVE_INFINITA_DATA_DIR"     --cold-store-dir "$LIVE_INFINITA_COLD_STORE_DIR" || true
}

restore_code() {
  (( CODE_DEPLOYED == 1 )) || return 0
  echo "[topology-006] Restaurando código anterior." >&2
  cp -a "$TMP/code/cold_engine.py" "$PROD_RUNTIME/cold_engine.py"
  cp -a "$TMP/code/autonomous_runtime.py" "$PROD_RUNTIME/autonomous_runtime.py"
}

rollback() {
  local rc=$?
  set +e
  if (( MIGRATED == 1 || CODE_DEPLOYED == 1 || WRITERS_PAUSED == 1 )); then
    systemctl stop live-infinita-autonomous-world.service live-infinita.service
    (( MIGRATED == 1 )) && restore_topology
    restore_code
    systemctl restart live-infinita-autonomous-world.service live-infinita.service
  fi
  rm -rf "$TMP"
  exit "$rc"
}
trap rollback ERR
echo "[topology-006] Validando código e topologia."
cd "$SOURCE_DIR"
python3 -m unittest   tests.test_nov_world_topology_006   tests.test_cold_authoritative_engine   tests.test_autonomous_runtime   tests.test_intent_planner
python3 -m py_compile   deploy/nov_world_topology_006.py   apps/world-runtime/cold_engine.py   apps/world-runtime/autonomous_runtime.py
"$PY" "$MIGRATION" --topology-file "$TOPOLOGY"

echo "[topology-006] Snapshot atômico e replay antes da migração."
BASELINE="$(snapshot baseline)"
verify_snapshot "$BASELINE"
write_old_topology "$BASELINE"

echo "[topology-006] Pausando writers por poucos segundos para migração atômica."
systemctl stop live-infinita-autonomous-world.service live-infinita.service
WRITERS_PAUSED=1
! systemctl is-active --quiet live-infinita-autonomous-world.service
! systemctl is-active --quiet live-infinita.service

echo "[topology-006] Aplicando topologia persistente como delta."
MIGRATION_OUT="$(
  PYTHONPATH="$SOURCE_DIR:$SOURCE_DIR/apps/world-runtime" "$PY" "$MIGRATION"     --apply     --topology-file "$TOPOLOGY"     --bootstrap-file "$LIVE_INFINITA_COLD_BOOTSTRAP_FILE"     --data-dir "$LIVE_INFINITA_DATA_DIR"     --cold-store-dir "$LIVE_INFINITA_COLD_STORE_DIR"
)"
echo "$MIGRATION_OUT"
if grep -q '"status": "applied"' <<<"$MIGRATION_OUT"; then
  MIGRATED=1
fi

echo "[topology-006] Snapshot pós-migração."
AFTER="$(snapshot after)"

echo "[topology-006] Validando regiões persistidas."
"$PY" - "$AFTER/data/world.json" <<'PY'
import json,sys
world=json.load(open(sys.argv[1],encoding="utf-8"))
regions={row.get("id"):row for row in world.get("regions",[]) if isinstance(row,dict)}
required={
    "clearing","shelter","deep_forest","river_crossing","village","ridge",
    "waterfall_overlook","watchtower","stone_circle","cave","meadow","ruins",
}
missing=sorted(required-set(regions))
if missing:
    raise SystemExit("missing regions: "+",".join(missing))
if len(regions) < 12:
    raise SystemExit(f"expected >=12 regions, got {len(regions)}")
print("TOPOLOGY_WORLD_OK", len(regions))
PY
echo "[topology-006] Instalando código de persistência."
install -o liveinfinita -g liveinfinita -m 0664   "$SOURCE_DIR/apps/world-runtime/cold_engine.py"   "$PROD_RUNTIME/cold_engine.py"
install -o liveinfinita -g liveinfinita -m 0664   "$SOURCE_DIR/apps/world-runtime/autonomous_runtime.py"   "$PROD_RUNTIME/autonomous_runtime.py"
CODE_DEPLOYED=1

systemctl restart live-infinita-autonomous-world.service live-infinita.service
WRITERS_PAUSED=0

echo "[topology-006] Replay pós-migração no snapshot estável enquanto a live já retorna."
verify_snapshot "$AFTER"

echo "[topology-006] Aguardando runtime."
for _ in $(seq 1 40); do
  if systemctl is-active --quiet live-infinita-autonomous-world.service      && systemctl is-active --quiet live-infinita.service      && curl -fsS --max-time 2 http://127.0.0.1:8080/api/health >/dev/null; then
    break
  fi
  sleep 1
done

systemctl is-active --quiet live-infinita-autonomous-world.service
systemctl is-active --quiet live-infinita.service
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null

echo "[topology-006] Confirmando API do World State."
curl -fsS --max-time 8 http://127.0.0.1:8080/api/world >"$TMP/world-api.json"
"$PY" - "$TMP/world-api.json" <<'PY'
import json,sys
world=json.load(open(sys.argv[1],encoding="utf-8"))
ids={str(row.get("id")) for row in world.get("regions",[]) if isinstance(row,dict)}
required={"river_crossing","village","ridge","waterfall_overlook","watchtower","stone_circle","cave","meadow","ruins"}
missing=sorted(required-ids)
if missing:
    raise SystemExit("API missing regions: "+",".join(missing))
print("TOPOLOGY_API_OK",len(ids),"sequence",world.get("sequence"))
PY

"$PY" "$SOURCE_DIR/deploy/check-spatial-region-descriptors.py"

MIGRATED=0
CODE_DEPLOYED=0
WRITERS_PAUSED=0
trap - ERR
rm -rf "$TMP"
echo "[topology-006] OK: mundo persistente expandido; replay, runtime e API válidos."
