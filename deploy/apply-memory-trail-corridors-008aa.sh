#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_TERRAIN="$REPO/apps/renderer-godot/world_map_cognitive_terrain.gd"
SRC_PREVIEW="$REPO/apps/renderer-godot/world_map_preview.gd"
DST_TERRAIN="$PROJECT/world_map_cognitive_terrain.gd"
DST_PREVIEW="$PROJECT/world_map_preview.gd"
SMOKE_CORRIDOR="$REPO/tests/godot_memory_trail_corridor_smoke.gd"
SMOKE_NATURAL="$REPO/tests/godot_cognitive_trail_naturalization_smoke.gd"
STATUS=/var/lib/live-infinita/render-runtime-status.json
BACKUP=/var/backups/live-infinita/008aa-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AA_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
for path in "$SRC_TERRAIN" "$SRC_PREVIEW" "$DST_TERRAIN" "$DST_PREVIEW" "$SMOKE_CORRIDOR" "$SMOKE_NATURAL"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'func _trail_decor_profile' "$SRC_TERRAIN" || fail "corredor cognitivo ausente"
grep -q 'role == "trail_edge"' "$SRC_PREVIEW" || fail "vegetação de borda ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST_TERRAIN" "$BACKUP/world_map_cognitive_terrain.gd"
cp -a "$DST_PREVIEW" "$BACKUP/world_map_preview.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AA_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_cognitive_terrain.gd" "$DST_TERRAIN" || true
    cp -a "$BACKUP/world_map_preview.gd" "$DST_PREVIEW" || true
    systemctl restart live-infinita-renderer.service || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008aa: source smokes =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE_NATURAL"
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE_CORRIDOR"

echo "== 008aa: install renderer files =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_TERRAIN" "$DST_TERRAIN"
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_PREVIEW" "$DST_PREVIEW"
grep -q 'func _trail_decor_profile' "$DST_TERRAIN" || fail "terrain instalado sem corredor"
grep -q 'role == "trail_edge"' "$DST_PREVIEW" || fail "preview instalado sem borda"

echo "== 008aa: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE_CORRIDOR"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi

echo "== 008aa: restart renderer =="
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

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
capture = int(data.get("capture_fps") or 0)
godot = int(data.get("godot_fps") or 0)
assert capture > 0, data
assert godot > 0, data
print(
    "RENDERER_008AA_OK",
    "capture_fps=", capture,
    "godot_fps=", godot,
    "governor=", bool(data.get("governor_enabled")),
)
PY

echo "== 008aa: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AA_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-renderer.service
df -h /

SUCCESS=1
echo "MEMORY_TRAIL_CORRIDORS_008AA_OK"
