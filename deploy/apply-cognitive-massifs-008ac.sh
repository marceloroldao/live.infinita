#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_TERRAIN="$REPO/apps/renderer-godot/world_map_cognitive_terrain.gd"
SRC_PREVIEW="$REPO/apps/renderer-godot/world_map_preview.gd"
DST_TERRAIN="$PROJECT/world_map_cognitive_terrain.gd"
DST_PREVIEW="$PROJECT/world_map_preview.gd"
SMOKE="$REPO/tests/godot_cognitive_massif_smoke.gd"
PY_TEST="$REPO/tests/test_cognitive_massifs_008ac.py"
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ac-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AC_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
for path in "$SRC_TERRAIN" "$SRC_PREVIEW" "$DST_TERRAIN" "$DST_PREVIEW" "$SMOKE" "$PY_TEST"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'func _rebuild_massifs' "$SRC_TERRAIN" || fail "massifs ausentes"
grep -q 'MAX_MASSIF_HEIGHT_M := 68.0' "$SRC_TERRAIN" || fail "limite de massif ausente"
grep -q 'massifs=%d' "$SRC_PREVIEW" || fail "telemetria de massif ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST_TERRAIN" "$BACKUP/world_map_cognitive_terrain.gd"
cp -a "$DST_PREVIEW" "$BACKUP/world_map_preview.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AC_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_cognitive_terrain.gd" "$DST_TERRAIN" || true
    cp -a "$BACKUP/world_map_preview.gd" "$DST_PREVIEW" || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ac: source tests =="
/opt/live.infinita/.venv/bin/python "$PY_TEST"
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE"

echo "== 008ac: install renderer files =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_TERRAIN" "$DST_TERRAIN"
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_PREVIEW" "$DST_PREVIEW"
grep -q 'func _rebuild_massifs' "$DST_TERRAIN" || fail "terrain instalado sem massifs"
grep -q 'massifs=%d' "$DST_PREVIEW" || fail "preview instalado sem telemetria"

echo "== 008ac: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ac-renderer-journal.log
rm -f "$journal_probe"

echo "== 008ac: restart renderer =="
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 60); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq 'WORLD_MAP_MEMORY_TERRAIN' "$journal_probe"        && grep -Fq 'massifs=' "$journal_probe"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer não confirmou massifs + world feed"
fi

massif_line="$(grep -F 'WORLD_MAP_MEMORY_TERRAIN' "$journal_probe" | tail -1)"
massif_count="$(printf '%s
' "$massif_line" | sed -n 's/.*massifs=\([0-9][0-9]*\).*/\1/p')"
[[ "$massif_count" =~ ^[0-9]+$ ]] || fail "contagem de massifs inválida"
(( massif_count <= 6 )) || fail "contagem de massifs excedeu limite"
echo "008AC_MASSIFS=$massif_count"

verified_mtime="$(stat -c %Y "$STATUS")"
sleep 10
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após iniciar massifs"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer parou"
grep -Fq "$EXPECTED_SCENE" "$STATUS" || fail "renderer perdeu cena 3D"

echo "== 008ac: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AC_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008ac-runtime-health.json
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
cat "$STATUS"
df -h /

SUCCESS=1
echo "COGNITIVE_MASSIFS_008AC_OK"
