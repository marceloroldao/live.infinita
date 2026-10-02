#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_FEATURES="$REPO/apps/renderer-godot/world_map_features.gd"
DST_FEATURES="$PROJECT/world_map_features.gd"
SMOKE="$REPO/tests/godot_static_feature_batching_smoke.gd"
PY_TEST="$REPO/tests/test_static_feature_batching_008ah.py"
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ah-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AH_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
for path in "$SRC_FEATURES" "$DST_FEATURES" "$SMOKE" "$PY_TEST"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'MultiMeshInstance3D.new()' "$SRC_FEATURES" || fail "MultiMesh ausente"
grep -q '"BridgePlanks"' "$SRC_FEATURES" || fail "batch de tábuas ausente"
grep -q '"BridgePosts"' "$SRC_FEATURES" || fail "batch de postes ausente"
grep -q '"StandingStones"' "$SRC_FEATURES" || fail "batch de stone circle ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST_FEATURES" "$BACKUP/world_map_features.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AH_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_features.gd" "$DST_FEATURES" || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ah: source tests =="
python3 "$PY_TEST"
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE"

echo "== 008ah: install features =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_FEATURES" "$DST_FEATURES"
grep -q 'MultiMeshInstance3D.new()' "$DST_FEATURES" || fail "features instalado sem MultiMesh"
grep -q '"BridgePlanks"' "$DST_FEATURES" || fail "features instalado sem batch da ponte"

echo "== 008ah: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ah-renderer-journal.log
rm -f "$journal_probe"

echo "== 008ah: restart renderer =="
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 60); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq '"render_width": 540' "$STATUS"        && grep -Fq '"render_height": 960' "$STATUS"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer não confirmou cena + world feed"
fi

verified_mtime="$(stat -c %Y "$STATUS")"
sleep 10
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após batching"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer parou"

echo "== 008ah: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AH_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008ah-runtime-health.json
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
cat "$STATUS"
df -h /

SUCCESS=1
echo "STATIC_FEATURE_BATCHING_008AH_OK"
