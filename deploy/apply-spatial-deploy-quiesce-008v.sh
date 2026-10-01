#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
BACKUP="$(mktemp -d /tmp/live-infinita-008v.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-spatial-deploy-quiesce-008v.sh" >&2
  exit 1
fi

backup_one() {
  local target="$1" rel="${1#/}"
  if [[ -e "$target" || -L "$target" ]]; then
    install -d "$BACKUP/$(dirname "$rel")"
    cp -a -- "$target" "$BACKUP/$rel"
  else
    printf '%s\n' "$target" >>"$ABSENT"
  fi
}

restore_one() {
  local target="$1" rel="${1#/}"
  if grep -Fxq -- "$target" "$ABSENT"; then
    rm -f -- "$target"
  elif [[ -e "$BACKUP/$rel" || -L "$BACKUP/$rel" ]]; then
    install -d "$(dirname "$target")"
    cp -a -- "$BACKUP/$rel" "$target"
  fi
}

TARGETS=(
  "$INSTALL/apps/world-runtime/nov_spatial_memory_sync.py"
  "$INSTALL/apps/world-runtime/cognitive_terrain_projection.py"
  "$INSTALL/apps/renderer-godot/world_map_cognitive_terrain.gd"
  "$INSTALL/apps/renderer-godot/world_map_traversability.gd"
  "$INSTALL/apps/renderer-godot/world_map_local_motion.gd"
  "$INSTALL/apps/renderer-godot/world_map_preview.gd"
  "/etc/systemd/system/live-infinita-nov-spatial-memory-sync.service"
  "/etc/systemd/system/live-infinita-nov-spatial-memory-sync.timer"
)
for target in "${TARGETS[@]}"; do backup_one "$target"; done

rollback() {
  local rc=$?
  trap - ERR
  set +e
  systemctl disable --now live-infinita-nov-spatial-memory-sync.timer >/dev/null 2>&1 || true
  for target in "${TARGETS[@]}"; do restore_one "$target"; done
  systemctl daemon-reload
  systemctl restart live-infinita.service >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008v] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

cd "$REPO"
python3 -m unittest tests.test_nov_spatial_memory_sync_008s tests.test_spatial_trajectory_batching_008t tests.test_spatial_corridor_recurrence_008u tests.test_cognitive_spatial_memory_008s tests.test_cognitive_terrain_008b tests.test_cognitive_traversability_008o tests.test_local_detour_routing_008p tests.test_cognitive_ecology_008q tests.test_cognitive_trails_008r

echo "[008v] Quiescendo sincronizador espacial anterior..."
systemctl disable --now live-infinita-nov-spatial-memory-sync.timer >/dev/null 2>&1 || true
systemctl stop live-infinita-nov-spatial-memory-sync.service >/dev/null 2>&1 || true
for _ in {1..20}; do
  state="$(systemctl show live-infinita-nov-spatial-memory-sync.service -p ActiveState --value 2>/dev/null || true)"
  case "$state" in
    ""|inactive|failed) break ;;
  esac
  sleep 1
done
state="$(systemctl show live-infinita-nov-spatial-memory-sync.service -p ActiveState --value 2>/dev/null || true)"
case "$state" in
  ""|inactive|failed) ;;
  *) echo "[008v] sync anterior ainda está em estado $state; abortando instalação." >&2; exit 1 ;;
esac
systemctl reset-failed live-infinita-nov-spatial-memory-sync.service >/dev/null 2>&1 || true

echo "[008v] Instalando ponte espacial e renderer..."
install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/world-runtime/nov_spatial_memory_sync.py" "$INSTALL/apps/world-runtime/nov_spatial_memory_sync.py"
install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/world-runtime/cognitive_terrain_projection.py" "$INSTALL/apps/world-runtime/cognitive_terrain_projection.py"
for name in world_map_cognitive_terrain.gd world_map_traversability.gd world_map_local_motion.gd world_map_preview.gd; do
  install -o liveinfinita -g liveinfinita -m 0644 "$REPO/apps/renderer-godot/$name" "$INSTALL/apps/renderer-godot/$name"
done
install -o root -g root -m 0644 "$REPO/deploy/live-infinita-nov-spatial-memory-sync.service" /etc/systemd/system/live-infinita-nov-spatial-memory-sync.service
install -o root -g root -m 0644 "$REPO/deploy/live-infinita-nov-spatial-memory-sync.timer" /etc/systemd/system/live-infinita-nov-spatial-memory-sync.timer

systemctl daemon-reload
grep -Fq 'MAX_EVENTS_PER_RUN = 1' "$INSTALL/apps/world-runtime/nov_spatial_memory_sync.py"
grep -Fq 'SPATIAL_RECURRENCE_GRID_M = 64.0' "$INSTALL/apps/world-runtime/cognitive_terrain_projection.py"
grep -Fq -- '--max-events 1' /etc/systemd/system/live-infinita-nov-spatial-memory-sync.service
echo "[008v] versão instalada confirmada: 1 trajetória/run + grid 64 m"
systemctl start live-infinita-nov-spatial-memory-sync.service
test -s /var/lib/live-infinita/memoria-local/nov-spatial-ingest.checkpoint.json
test -s /var/lib/live-infinita/memoria-local/structural-observations/index.jsonl
test -s /var/lib/live-infinita/memoria-local/structural-observations/persistence/memoria.sqlite3
systemctl start live-infinita-cognitive-terrain.service

python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('/var/lib/live-infinita/cognitive-terrain/projection.json').read_text())
assert d['schema']=='live-infinita-cognitive-terrain/v1'
assert d['policy']['visual_only'] is True
assert d['policy']['world_write_authority'] is False
assert d['source']['spatial_observations'] > 0
assert len(d['spatial_trails']) <= d['policy']['max_spatial_trails']
print('projection_id='+d['projection_id'])
print('spatial_observations='+str(d['source']['spatial_observations']))
print('spatial_trails='+str(len(d['spatial_trails'])))
print('xy_candidates='+str(sum(bool(x['trail_candidate']) for x in d['spatial_trails'])))
PY

systemctl enable --now live-infinita-nov-spatial-memory-sync.timer >/dev/null
systemctl restart live-infinita.service

for _ in {1..30}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8080/api/health >/tmp/live-008v-health.json 2>/dev/null; then break; fi
  sleep 1
done
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path('/tmp/live-008v-health.json').read_text())
assert d.get('ok') is True
assert d.get('replay_ok') is True
print('runtime_health=ok replay_ok=true')
PY
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-nov-spatial-memory-sync.timer
systemctl is-active --quiet live-infinita-cognitive-terrain.timer

echo "[008v] Publicando preview Web..."
bash "$REPO/deploy/export-world-map-preview-web.sh"

trap - ERR
rm -rf -- "$BACKUP"
echo "[008v] OK: delta confirmado -> StructuralEvent Memoria.ia -> trilha XY visual."
