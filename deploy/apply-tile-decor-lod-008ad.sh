#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PY=/opt/live.infinita/.venv/bin/python
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC="$REPO/apps/renderer-godot/world_map_preview.gd"
DST="$PROJECT/world_map_preview.gd"
SMOKE="$REPO/tests/godot_tile_decor_lod_smoke.gd"
PY_TEST="$REPO/tests/test_tile_decor_lod_008ad.py"
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ad-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AD_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
[[ -x $PY ]] || fail "Python da Live ausente"
for path in "$SRC" "$DST" "$SMOKE" "$PY_TEST"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'const MAX_ACTIVE_DECOR := 22' "$SRC" || fail "LOD 22 ausente"
grep -q 'func _decor_indices_for_tile' "$SRC" || fail "função LOD ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST" "$BACKUP/world_map_preview.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AD_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_preview.gd" "$DST" || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ad: source test =="
"$PY" "$PY_TEST"

echo "== 008ad: install preview =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC" "$DST"
grep -q 'const MAX_ACTIVE_DECOR := 22' "$DST" || fail "arquivo instalado sem LOD"
grep -q 'func _decor_indices_for_tile' "$DST" || fail "arquivo instalado sem função LOD"

echo "== 008ad: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ad-renderer-journal.log
rm -f "$journal_probe"

echo "== 008ad: restart renderer =="
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 60); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq 'WORLD_MAP_PREVIEW_READY' "$journal_probe"        && grep -Fq 'decor=22' "$journal_probe"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer não confirmou LOD + world feed"
fi

echo "== 008ad: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AD_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
cat "$STATUS"
df -h /

SUCCESS=1
echo "TILE_DECOR_LOD_008AD_OK"
