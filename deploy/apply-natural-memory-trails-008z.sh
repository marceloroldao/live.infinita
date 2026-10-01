#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
DEPLOYED=/opt/live.infinita/apps/renderer-godot/world_map_cognitive_terrain.gd
SOURCE="$REPO/apps/renderer-godot/world_map_cognitive_terrain.gd"
SMOKE="$REPO/tests/godot_cognitive_trail_naturalization_smoke.gd"
PROJECT=/opt/live.infinita/apps/renderer-godot
STATUS=/var/lib/live-infinita/render-runtime-status.json
BACKUP=/var/backups/live-infinita/008z-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008Z_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
[[ -f $SOURCE ]] || fail "fonte 008z ausente"
[[ -f $SMOKE ]] || fail "smoke 008z ausente"
[[ -f $DEPLOYED ]] || fail "renderer instalado ausente"
grep -q 'func _natural_trail_point(' "$SOURCE" || fail "fonte sem naturalização"
grep -q 'MAX_TRAIL_MEANDER_M := 4.5' "$SOURCE" || fail "limite de meandro ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DEPLOYED" "$BACKUP/world_map_cognitive_terrain.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008Z_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_cognitive_terrain.gd" "$DEPLOYED" || true
    systemctl restart live-infinita-renderer.service || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008z: source smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE"

echo "== 008z: install renderer source =="
install -o liveinfinita -g liveinfinita -m 0664 "$SOURCE" "$DEPLOYED"
grep -q 'func _natural_trail_point(' "$DEPLOYED" || fail "arquivo instalado sem naturalização"

echo "== 008z: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi

echo "== 008z: restart native renderer =="
systemctl restart live-infinita-renderer.service
for _ in $(seq 1 40); do
  if systemctl is-active --quiet live-infinita-renderer.service && [[ -f "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    if (( current_mtime > before_mtime )); then
      break
    fi
  fi
  sleep 1
done
systemctl is-active --quiet live-infinita-renderer.service || fail "renderer não ficou ativo"

python3 - "$STATUS" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
capture = int(data.get("capture_fps") or 0)
godot = int(data.get("godot_fps") or 0)
assert capture > 0, data
assert godot > 0, data
print(
    "RENDERER_008Z_OK",
    "capture_fps=", capture,
    "godot_fps=", godot,
    "governor=", bool(data.get("governor_enabled")),
)
PY

echo "== 008z: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008Z_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-renderer.service
df -h /

SUCCESS=1
echo "NATURAL_MEMORY_TRAILS_008Z_OK"
