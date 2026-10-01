#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_PREVIEW="$REPO/apps/renderer-godot/world_map_preview.gd"
DST_PREVIEW="$PROJECT/world_map_preview.gd"
SMOKE="$REPO/tests/godot_tile_cache_smoke.gd"
PY_TEST="$REPO/tests/test_tile_cache_008af.py"
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008af-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AF_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
for path in "$SRC_PREVIEW" "$DST_PREVIEW" "$SMOKE" "$PY_TEST"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'MAX_CACHED_TILES := 24' "$SRC_PREVIEW" || fail "cache limitado ausente"
grep -q 'WORLD_MAP_TILE_CACHE hits=' "$SRC_PREVIEW" || fail "telemetria do cache ausente"

install -d -m 0700 "$BACKUP"
cp -a "$DST_PREVIEW" "$BACKUP/world_map_preview.gd"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AF_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/world_map_preview.gd" "$DST_PREVIEW" || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008af: source tests =="
python3 "$PY_TEST"
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$REPO/apps/renderer-godot" --script "$SMOKE"

echo "== 008af: install preview =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_PREVIEW" "$DST_PREVIEW"
grep -q 'MAX_CACHED_TILES := 24' "$DST_PREVIEW" || fail "preview instalado sem cache"
grep -q 'WORLD_MAP_TILE_CACHE hits=' "$DST_PREVIEW" || fail "preview instalado sem telemetria"

echo "== 008af: deployed smoke =="
GODOT_SILENCE_ROOT_WARNING=1 "$ENGINE" --headless --path "$PROJECT" --script "$SMOKE"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008af-renderer-journal.log
rm -f "$journal_probe"

echo "== 008af: restart renderer =="
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

echo "== 008af: wait for real cache hit =="
cache_hit=0
for _ in $(seq 1 120); do
  journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
  if grep -Fq 'WORLD_MAP_TILE_CACHE hits=' "$journal_probe"; then
    cache_hit=1
    break
  fi
  sleep 1
done

if [[ "$cache_hit" != "1" ]]; then
  tail -100 "$journal_probe" || true
  fail "cache não registrou hit no feed real"
fi

cache_line="$(grep -F 'WORLD_MAP_TILE_CACHE hits=' "$journal_probe" | tail -1)"
echo "008AF_CACHE=$cache_line"

verified_mtime="$(stat -c %Y "$STATUS")"
sleep 10
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após cache"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer parou"

journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
ready_count="$(grep -c 'WORLD_MAP_TILE_READY' "$journal_probe" || true)"
cache_count="$(grep -c 'WORLD_MAP_TILE_CACHE hits=' "$journal_probe" || true)"
echo "008AF_TILE_READY_LINES=$ready_count"
echo "008AF_CACHE_TELEMETRY_LINES=$cache_count"

echo "== 008af: web preview =="
WEB_PREVIEW_RESULT=preserved
if bash "$REPO/deploy/export-world-map-preview-web.sh"; then
  WEB_PREVIEW_RESULT=updated
fi
echo "008AF_WEB_PREVIEW=$WEB_PREVIEW_RESULT"

curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008af-runtime-health.json
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
cat "$STATUS"
df -h /

SUCCESS=1
echo "TILE_CACHE_008AF_OK"
