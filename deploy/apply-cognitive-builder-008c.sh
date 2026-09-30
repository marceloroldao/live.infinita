#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
DROPIN_DIR=/etc/systemd/system/live-infinita-autonomous-world.service.d
DROPIN="$DROPIN_DIR/40-world-builder.conf"
BACKUP="$(mktemp -d /tmp/live-infinita-008c.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-cognitive-builder-008c.sh" >&2
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
  "$INSTALL/apps/world-runtime/cognitive_world_builder.py"
  "$INSTALL/apps/world-runtime/autonomous_runtime.py"
  "$INSTALL/apps/world-runtime/autonomous_runtime_main.py"
  "$INSTALL/apps/world-runtime/world_tick.py"
  "$DROPIN"
)

for target in "${TARGETS[@]}"; do
  backup_one "$target"
done

rollback() {
  local rc=$?
  trap - ERR
  set +e
  for target in "${TARGETS[@]}"; do
    restore_one "$target"
  done
  systemctl daemon-reload
  systemctl restart live-infinita-autonomous-world.service >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008c] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

test -s /var/lib/live-infinita/cognitive-terrain/projection.json
systemctl is-active --quiet live-infinita-cognitive-terrain.timer
systemctl is-active --quiet live-infinita-memoria-local.service

echo "[008c] Instalando agente construtor no single writer..."
for name in cognitive_world_builder.py autonomous_runtime.py autonomous_runtime_main.py world_tick.py; do
  install -o liveinfinita -g liveinfinita -m 0644     "$REPO/apps/world-runtime/$name"     "$INSTALL/apps/world-runtime/$name"
done

install -d -o root -g root -m 0755 "$DROPIN_DIR"
install -o root -g root -m 0644   "$REPO/deploy/live-infinita-autonomous-world-builder.conf"   "$DROPIN"

systemctl daemon-reload
systemctl restart live-infinita-autonomous-world.service

for _ in {1..30}; do
  if systemctl is-active --quiet live-infinita-autonomous-world.service; then
    break
  fi
  sleep 1
done
systemctl is-active --quiet live-infinita-autonomous-world.service
sleep 2

state="$(systemctl show live-infinita-autonomous-world.service   -p ActiveState -p SubState -p Result -p NRestarts -p MainPID -p Environment --no-pager)"
printf '%s\n' "$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER=1' <<<"$state"
grep -q 'LIVE_INFINITA_WORLD_BUILDER_INTERVAL_TICKS=240' <<<"$state"
grep -q 'LIVE_INFINITA_COGNITIVE_TERRAIN_FILE=/var/lib/live-infinita/cognitive-terrain/projection.json' <<<"$state"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008c-health.json
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008c-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/live-infinita/autonomous-world/simulation-clock.json")
d=json.loads(p.read_text())
tick=int(d.get("tick",0))
interval=240
next_tick=((tick // interval) + 1) * interval
print(f"current_tick={tick}")
print(f"next_builder_tick={next_tick}")
print(f"ticks_until_builder={next_tick-tick}")
print("builder_policy=max_1_creation_per_cycle global_cap=48")
PY

# Main runtime/renderer/narrator are deliberately not restarted by 008C.
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-cognitive-terrain.timer

trap - ERR
rm -rf -- "$BACKUP"
echo "[008c] OK: construtor habilitado dentro do autonomous-world; toda criação continua passando pelo MutationGate."
