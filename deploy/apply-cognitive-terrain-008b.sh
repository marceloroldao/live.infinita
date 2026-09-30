#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL=/opt/live.infinita
BACKUP="$(mktemp -d /tmp/live-infinita-008b.XXXXXX)"
ABSENT="$BACKUP/absent.txt"
touch "$ABSENT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-cognitive-terrain-008b.sh" >&2
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
  "$INSTALL/apps/world-runtime/main_spatial.py"
  "$INSTALL/apps/world-runtime/cognitive_terrain_projection.py"
  "$INSTALL/apps/renderer-godot/world_map_preview.gd"
  "$INSTALL/apps/renderer-godot/world_map_live_feed.gd"
  "$INSTALL/apps/renderer-godot/world_map_live_visual.gd"
  "$INSTALL/apps/renderer-godot/world_map_cognitive_terrain.gd"
  "/etc/systemd/system/live-infinita-cognitive-terrain.service"
  "/etc/systemd/system/live-infinita-cognitive-terrain.timer"
)

for target in "${TARGETS[@]}"; do
  backup_one "$target"
done

rollback() {
  local rc=$?
  trap - ERR
  set +e
  systemctl disable --now live-infinita-cognitive-terrain.timer >/dev/null 2>&1 || true
  for target in "${TARGETS[@]}"; do
    restore_one "$target"
  done
  systemctl daemon-reload
  systemctl restart live-infinita.service >/dev/null 2>&1 || true
  rm -rf -- "$BACKUP"
  echo "[008b] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

echo "[008b] Instalando projeção cognitiva..."
install -o liveinfinita -g liveinfinita -m 0644   "$REPO/apps/world-runtime/main_spatial.py"   "$INSTALL/apps/world-runtime/main_spatial.py"
install -o liveinfinita -g liveinfinita -m 0644   "$REPO/apps/world-runtime/cognitive_terrain_projection.py"   "$INSTALL/apps/world-runtime/cognitive_terrain_projection.py"

for name in world_map_preview.gd world_map_live_feed.gd world_map_live_visual.gd world_map_cognitive_terrain.gd; do
  install -o liveinfinita -g liveinfinita -m 0644     "$REPO/apps/renderer-godot/$name"     "$INSTALL/apps/renderer-godot/$name"
done

install -o root -g root -m 0644   "$REPO/deploy/live-infinita-cognitive-terrain.service"   /etc/systemd/system/live-infinita-cognitive-terrain.service
install -o root -g root -m 0644   "$REPO/deploy/live-infinita-cognitive-terrain.timer"   /etc/systemd/system/live-infinita-cognitive-terrain.timer
install -d -o liveinfinita -g liveinfinita -m 0750 /var/lib/live-infinita/cognitive-terrain

systemctl daemon-reload
systemctl start live-infinita-cognitive-terrain.service

python3 - <<'PY'
import json
from pathlib import Path
p=Path("/var/lib/live-infinita/cognitive-terrain/projection.json")
d=json.loads(p.read_text())
assert d["schema"] == "live-infinita-cognitive-terrain/v1"
assert d["policy"]["visual_only"] is True
assert d["policy"]["world_write_authority"] is False
assert d["policy"]["selection_authority"] is False
assert len(d["regions"]) <= 32
assert len(d["transitions"]) <= 48
print("projection_id=" + d["projection_id"])
print("nov_observations=" + str(d["source"]["nov_observations"]))
print("regions=" + str(len(d["regions"])) + " transitions=" + str(len(d["transitions"])))
print("uplifts=" + ",".join(r["region_id"] for r in d["regions"] if r["terrain_role"] == "uplift"))
print("basins=" + ",".join(r["region_id"] for r in d["regions"] if r["terrain_role"] == "basin"))
PY

systemctl enable --now live-infinita-cognitive-terrain.timer >/dev/null
systemctl restart live-infinita.service

for _ in {1..30}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8080/api/health >/tmp/live-008b-health.json 2>/dev/null; then
    break
  fi
  sleep 1
done
python3 - <<'PY'
import json
from pathlib import Path
d=json.loads(Path("/tmp/live-008b-health.json").read_text())
assert d.get("ok") is True
assert d.get("replay_ok") is True
print("runtime_health=ok replay_ok=true")
PY

systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-cognitive-terrain.timer
systemctl show live-infinita-cognitive-terrain.timer   -p ActiveState -p SubState -p Result --no-pager

echo "[008b] Publicando preview Web com smoke/rollback próprio..."
bash "$REPO/deploy/export-world-map-preview-web.sh"

trap - ERR
rm -rf -- "$BACKUP"
echo "[008b] OK: Memoria.ia -> campo cognitivo -> relevo/lago visual; World State permanece somente leitura."
