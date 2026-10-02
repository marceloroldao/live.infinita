#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_VISUAL="$REPO/apps/renderer-godot/world_map_live_visual.gd"
DST_VISUAL="$PROJECT/world_map_live_visual.gd"
SMOKE="$REPO/tests/godot_region_visual_batching_smoke.gd"
PY_TEST="$REPO/tests/test_region_visual_batching_008ai.py"
MAP_TEST="$REPO/tests/test_world_map_001.py"
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ai-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AI_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
for path in "$SRC_VISUAL" "$DST_VISUAL" "$SMOKE" "$PY_TEST" "$MAP_TEST"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done

grep -q 'MAX_REGION_LABELS := 4' "$SRC_VISUAL" || fail "limite de labels ausente"
grep -q '"RegionRings"' "$SRC_VISUAL" || fail "batch de anéis ausente"
grep -q 'WORLD_MAP_REGION_VISUAL' "$SRC_VISUAL" || fail "telemetria regional ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST_VISUAL" "$BACKUP/world_map_live_visual.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AI_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_live_visual.gd" "$DST_VISUAL" || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ai: source tests =="
python3 "$PY_TEST"
python3 "$MAP_TEST"
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE"

echo "== 008ai: install visual =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_VISUAL" "$DST_VISUAL"
grep -q 'MAX_REGION_LABELS := 4' "$DST_VISUAL" || fail "visual instalado sem limite"
grep -q '"RegionRings"' "$DST_VISUAL" || fail "visual instalado sem batch"

echo "== 008ai: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ai-renderer-journal.log
rm -f "$journal_probe"

echo "== 008ai: restart renderer =="
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 75); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq '"render_width": 540' "$STATUS"        && grep -Fq '"render_height": 960' "$STATUS"        && grep -Fq 'WORLD_MAP_REGION_VISUAL' "$journal_probe"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer não confirmou region visual + world feed"
fi

region_line="$(grep -F 'WORLD_MAP_REGION_VISUAL' "$journal_probe" | tail -1)"
echo "008AI_REGION=$region_line"

verified_mtime="$(stat -c %Y "$STATUS")"
sleep 10
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após batching regional"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer parou"

echo "== 008ai: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AI_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008ai-runtime-health.json
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
cat "$STATUS"
df -h /

SUCCESS=1
echo "REGION_OVERLAY_BATCHING_008AI_OK"
