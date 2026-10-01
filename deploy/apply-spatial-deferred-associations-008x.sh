#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
MEM_REPO=/home/etbra/_memoria_local_probe
MEM_SHA=1c5560423a015945c2b81e9e79a9dfa60298166e
CORE=/opt/live-infinita-memoria-core/$MEM_SHA
MEM_UNIT=/etc/systemd/system/live-infinita-memoria-local.service
MEM_ENV=/etc/live-infinita/memoria-local.env
SPATIAL_UNIT=live-infinita-nov-spatial-memory-sync.service
SPATIAL_TIMER=live-infinita-nov-spatial-memory-sync.timer
SYNC_DST=/opt/live.infinita/apps/world-runtime/nov_spatial_memory_sync.py
PROJ_DST=/opt/live.infinita/apps/world-runtime/cognitive_terrain_projection.py
BACKUP=/var/backups/live-infinita/008x-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008X_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -d $REPO/.git ]] || fail "repo Live.infinita ausente"
[[ -d $MEM_REPO/.git ]] || fail "clone Memoria.ia ausente"
[[ "$(git -C "$MEM_REPO" rev-parse HEAD)" == "$MEM_SHA" ]] || fail "Memoria.ia HEAD inesperado"
grep -q 'defer_associations=true' "$REPO/apps/world-runtime/nov_spatial_memory_sync.py" || fail "cliente 008x ausente"
grep -q 'SPATIAL_RECURRENCE_GRID_M = 64.0' "$REPO/apps/world-runtime/cognitive_terrain_projection.py" || fail "grid 64m ausente"

install -d -m 0700 "$BACKUP"
cp -a "$MEM_UNIT" "$BACKUP/memoria-local.service"
cp -a "$MEM_ENV" "$BACKUP/memoria-local.env"
cp -a "$SYNC_DST" "$BACKUP/nov_spatial_memory_sync.py"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008X_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/memoria-local.service" "$MEM_UNIT"
    cp -a "$BACKUP/memoria-local.env" "$MEM_ENV"
    cp -a "$BACKUP/nov_spatial_memory_sync.py" "$SYNC_DST"
    systemctl daemon-reload || true
    systemctl restart live-infinita-memoria-local.service || true
    systemctl enable --now "$SPATIAL_TIMER" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008x: quiesce =="
systemctl disable --now "$SPATIAL_TIMER" || true
systemctl stop "$SPATIAL_UNIT" || true
systemctl stop live-infinita-memoria-local.service || true
systemctl reset-failed "$SPATIAL_UNIT" live-infinita-memoria-local.service || true

echo "== 008x: core Memoria.ia versionado =="
rm -rf "$CORE.tmp"
install -d -m 0755 "$CORE.tmp/src"
cp -a "$MEM_REPO/src/." "$CORE.tmp/src/"
chown -R root:root "$CORE.tmp"
chmod -R a+rX "$CORE.tmp"
rm -rf "$CORE"
mv "$CORE.tmp" "$CORE"

grep -q 'MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN' "$CORE/src/memoria_resolutiva/product_server.py" || fail "core sem controle de replay"
grep -q 'association_sync_deferred' "$CORE/src/memoria_resolutiva/product_structural.py" || fail "core sem ingest diferido"

echo "== 008x: unit/env local =="
sed -Ei "s#/opt/live-infinita-memoria-core/[0-9a-f]{40}/src#/opt/live-infinita-memoria-core/$MEM_SHA/src#g" "$MEM_UNIT"
if grep -q '^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=' "$MEM_ENV"; then
  sed -Ei 's/^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=.*/MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0/' "$MEM_ENV"
else
  printf '\nMEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0\n' >> "$MEM_ENV"
fi

grep -q "$MEM_SHA/src/memoria_resolutiva/product_server.py" "$MEM_UNIT" || fail "ConditionPath do core não atualizado"
grep -q "PYTHONPATH=/opt/live-infinita-memoria-core/$MEM_SHA/src" "$MEM_UNIT" || fail "PYTHONPATH do core não atualizado"
grep -q '^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0$' "$MEM_ENV" || fail "replay_on_open não desabilitado"

echo "== 008x: cliente Live =="
install -o liveinfinita -g liveinfinita -m 0664   "$REPO/apps/world-runtime/nov_spatial_memory_sync.py" "$SYNC_DST"
install -o liveinfinita -g liveinfinita -m 0664   "$REPO/apps/world-runtime/cognitive_terrain_projection.py" "$PROJ_DST"
grep -q 'defer_associations=true' "$SYNC_DST" || fail "cliente instalado sem defer"
grep -q 'association_sync_deferred' "$SYNC_DST" || fail "ACK guard instalado ausente"
grep -q 'MAX_EVENTS_PER_RUN = 1' "$SYNC_DST" || fail "limite 1/run ausente"

echo "== 008x: start Memoria.ia =="
systemctl daemon-reload
systemctl start live-infinita-memoria-local.service

health=/tmp/live-008x-memoria-health.json
rm -f "$health"
for _ in $(seq 1 40); do
  if curl -fsS --max-time 3 http://127.0.0.1:8788/api/v1/storage/health > "$health"; then
    break
  fi
  sleep 1
done
[[ -s "$health" ]] || {
  systemctl status live-infinita-memoria-local.service --no-pager -n 80 || true
  journalctl -u live-infinita-memoria-local.service -n 120 --no-pager || true
  fail "Memoria.ia não abriu 8788"
}

python3 - "$health" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d.get("status") == "ok", d
print("MEMORIA_HEALTH_OK",
      "raw=", d.get("structural_observations"),
      "derived=", d.get("structural_association_observations"),
      "pending=", d.get("structural_association_pending"))
PY

echo "== 008x: one-shot espacial diferido =="
systemctl reset-failed "$SPATIAL_UNIT" || true
systemctl start "$SPATIAL_UNIT"
journalctl -u "$SPATIAL_UNIT" -n 80 --no-pager | tail -40
journalctl -u "$SPATIAL_UNIT" -n 80 --no-pager | grep -q 'NOV_SPATIAL_MEMORY_SYNC_OK'   || fail "sync espacial não confirmou sucesso"

echo "== 008x: projeção cognitiva =="
systemctl start live-infinita-cognitive-terrain.service
projection=/var/lib/live-infinita/cognitive-terrain/projection.json
[[ -s "$projection" ]] || fail "projection.json ausente"
python3 - "$projection" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
p=d.get("policy") or {}
trails=d.get("spatial_trails") or []
candidates=[t for t in trails if t.get("trail_candidate") is True]
counts=[int(t.get("count",0)) for t in candidates]
print("COGNITIVE_008X_OK",
      "grid=", p.get("spatial_recurrence_grid_m"),
      "observations=", d.get("spatial_observations"),
      "trails=", len(trails),
      "candidates=", len(candidates),
      "max_count=", max(counts, default=0))
assert p.get("spatial_recurrence_grid_m") == 64.0
PY

echo "== 008x: reativando runtime =="
systemctl enable --now "$SPATIAL_TIMER"
systemctl restart live-infinita.service

runtime_health=/tmp/live-008x-runtime-health.json
curl -fsS --max-time 12 http://127.0.0.1:8080/api/health > "$runtime_health"
python3 - "$runtime_health" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d.get("ok") is True, d
print("LIVE_RUNTIME_HEALTH_OK")
PY

systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SPATIAL_TIMER"

echo "== 008x: estado final =="
systemctl show live-infinita-memoria-local.service   -p ActiveState -p SubState -p MainPID -p NRestarts -p MemoryCurrent
df -h /
SUCCESS=1
echo "SPATIAL_DEFERRED_ASSOCIATIONS_008X_OK"
