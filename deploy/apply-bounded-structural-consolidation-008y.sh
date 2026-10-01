#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
MEM_REPO=/home/etbra/_memoria_local_probe
MEM_SHA=dfd87c995b50c49b45a9d5dd4c43cce456983d4f
CORE=/opt/live-infinita-memoria-core/$MEM_SHA
MEM_UNIT=/etc/systemd/system/live-infinita-memoria-local.service
MEM_ENV=/etc/live-infinita/memoria-local.env
SPATIAL_TIMER=live-infinita-nov-spatial-memory-sync.timer
CONSOLIDATOR_SERVICE=live-infinita-structural-association-consolidator.service
CONSOLIDATOR_TIMER=live-infinita-structural-association-consolidator.timer
CONSOLIDATOR_DST=/opt/live.infinita/apps/world-runtime/structural_association_consolidator.py
BACKUP=/var/backups/live-infinita/008y-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008Y_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -d $REPO/.git ]] || fail "repo Live.infinita ausente"
[[ -d $MEM_REPO/.git ]] || fail "clone Memoria.ia ausente"
[[ "$(git -C "$MEM_REPO" rev-parse HEAD)" == "$MEM_SHA" ]] || fail "Memoria.ia HEAD inesperado"
grep -q 'max_observations' "$MEM_REPO/src/memoria_resolutiva/product_structural.py" || fail "core sem sync limitado"
grep -q 'MAX_OBSERVATIONS_PER_RUN = 16' "$REPO/apps/world-runtime/structural_association_consolidator.py" || fail "cliente 008y ausente"

install -d -m 0700 "$BACKUP"
cp -a "$MEM_UNIT" "$BACKUP/memoria-local.service"
cp -a "$MEM_ENV" "$BACKUP/memoria-local.env"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008Y_ROLLBACK rc=$rc" >&2
    systemctl disable --now "$CONSOLIDATOR_TIMER" 2>/dev/null || true
    cp -a "$BACKUP/memoria-local.service" "$MEM_UNIT"
    cp -a "$BACKUP/memoria-local.env" "$MEM_ENV"
    systemctl daemon-reload || true
    systemctl restart live-infinita-memoria-local.service || true
    systemctl enable --now "$SPATIAL_TIMER" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008y: quiesce =="
systemctl disable --now "$SPATIAL_TIMER" || true
systemctl disable --now "$CONSOLIDATOR_TIMER" 2>/dev/null || true
systemctl stop "$CONSOLIDATOR_SERVICE" 2>/dev/null || true
systemctl stop live-infinita-memoria-local.service || true

echo "== 008y: core Memoria.ia versionado =="
rm -rf "$CORE.tmp"
install -d -m 0755 "$CORE.tmp/src"
cp -a "$MEM_REPO/src/." "$CORE.tmp/src/"
chown -R root:root "$CORE.tmp"
chmod -R a+rX "$CORE.tmp"
rm -rf "$CORE"
mv "$CORE.tmp" "$CORE"

grep -q 'max_observations' "$CORE/src/memoria_resolutiva/structural_association_runtime.py" || fail "runtime sem limite"
grep -q 'COMPACT_POINTER_FORMAT' "$CORE/src/memoria_resolutiva/structural_association_runtime.py" || fail "runtime sem checkpoint compacto"
grep -q 'max_observations' "$CORE/src/memoria_resolutiva/product_structural.py" || fail "endpoint sem limite"

echo "== 008y: unit/env Memoria.ia =="
sed -Ei "s#/opt/live-infinita-memoria-core/[0-9a-f]{40}/src#/opt/live-infinita-memoria-core/$MEM_SHA/src#g" "$MEM_UNIT"
if grep -q '^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=' "$MEM_ENV"; then
  sed -Ei 's/^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=.*/MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0/' "$MEM_ENV"
else
  printf '\nMEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0\n' >> "$MEM_ENV"
fi

grep -q "$MEM_SHA/src/memoria_resolutiva/product_server.py" "$MEM_UNIT" || fail "ConditionPath não atualizado"
grep -q "PYTHONPATH=/opt/live-infinita-memoria-core/$MEM_SHA/src" "$MEM_UNIT" || fail "PYTHONPATH não atualizado"
grep -q '^MEMORIA_STRUCTURAL_ASSOCIATIONS_REPLAY_ON_OPEN=0$' "$MEM_ENV" || fail "replay_on_open incorreto"

echo "== 008y: consolidator =="
install -o liveinfinita -g liveinfinita -m 0664   "$REPO/apps/world-runtime/structural_association_consolidator.py" "$CONSOLIDATOR_DST"
install -o root -g root -m 0644   "$REPO/deploy/$CONSOLIDATOR_SERVICE" "/etc/systemd/system/$CONSOLIDATOR_SERVICE"
install -o root -g root -m 0644   "$REPO/deploy/$CONSOLIDATOR_TIMER" "/etc/systemd/system/$CONSOLIDATOR_TIMER"

echo "== 008y: start Memoria.ia =="
systemctl daemon-reload
systemctl start live-infinita-memoria-local.service

health=/tmp/live-008y-memoria-health.json
rm -f "$health"
for _ in $(seq 1 90); do
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

before_pending="$(python3 - "$health" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d.get("status") == "ok", d
print(int(d.get("structural_association_pending") or 0))
PY
)"
echo "008Y_PENDING_BEFORE=$before_pending"

echo "== 008y: one-shot consolidator =="
systemctl reset-failed "$CONSOLIDATOR_SERVICE" 2>/dev/null || true
if ! systemctl start "$CONSOLIDATOR_SERVICE"; then
  journalctl -u "$CONSOLIDATOR_SERVICE" -n 80 --no-pager || true
  fail "consolidação limitada falhou"
fi
consolidator_result="$(systemctl show "$CONSOLIDATOR_SERVICE" -p Result --value)"
consolidator_exec_status="$(systemctl show "$CONSOLIDATOR_SERVICE" -p ExecMainStatus --value)"
journalctl -u "$CONSOLIDATOR_SERVICE" -n 30 --no-pager || true
[[ "$consolidator_result" == "success" && "$consolidator_exec_status" == "0" ]]   || fail "consolidator result=$consolidator_result status=$consolidator_exec_status"

after=/tmp/live-008y-memoria-health-after.json
curl -fsS --max-time 5 http://127.0.0.1:8788/api/v1/storage/health > "$after"
after_pending="$(python3 - "$after" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
print(int(d.get("structural_association_pending") or 0))
PY
)"
checkpoint_format="$(python3 - "$after" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
print(d.get("structural_association_checkpoint_format") or "")
PY
)"
echo "008Y_PENDING_AFTER=$after_pending"
echo "008Y_CHECKPOINT_FORMAT=$checkpoint_format"
(( after_pending <= before_pending )) || fail "backlog aumentou durante validação isolada"
[[ "$checkpoint_format" == "memoria.ia-structural-association-pointer-v2" ]]   || fail "checkpoint compacto não foi ativado"

echo "== 008y: timers =="
systemctl enable --now "$CONSOLIDATOR_TIMER"
systemctl enable --now "$SPATIAL_TIMER"

runtime_health=/tmp/live-008y-runtime-health.json
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health > "$runtime_health"
python3 - "$runtime_health" <<'PY'
import json, sys
d=json.load(open(sys.argv[1], encoding="utf-8"))
assert d.get("ok") is True, d
print("LIVE_RUNTIME_HEALTH_OK")
PY

systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet "$CONSOLIDATOR_TIMER"
systemctl is-active --quiet "$SPATIAL_TIMER"

echo "== 008y: estado final =="
systemctl show live-infinita-memoria-local.service   -p ActiveState -p SubState -p MainPID -p NRestarts -p MemoryCurrent
systemctl show "$CONSOLIDATOR_SERVICE"   -p Result -p ExecMainStatus -p ActiveState -p SubState
df -h /

SUCCESS=1
echo "BOUNDED_STRUCTURAL_CONSOLIDATION_008Y_OK"
