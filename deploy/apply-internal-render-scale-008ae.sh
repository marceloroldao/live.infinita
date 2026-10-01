#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
SRC_RENDERER="$REPO/apps/headless-renderer/headless_renderer.py"
SRC_UNIT="$REPO/deploy/live-infinita-renderer.service"
DST_RENDERER=/opt/live.infinita/apps/headless-renderer/headless_renderer.py
DST_UNIT=/etc/systemd/system/live-infinita-renderer.service
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ae-$(date -u +%Y%m%dT%H%M%SZ)

fail() { echo "008AE_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $PY ]] || fail "Python da Live ausente"
for path in "$SRC_RENDERER" "$SRC_UNIT" "$DST_RENDERER" "$DST_UNIT"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
grep -q 'LIVE_INFINITA_RENDER_INTERNAL_WIDTH' "$SRC_RENDERER" || fail "renderer sem escala interna"
grep -q 'LIVE_INFINITA_RENDER_INTERNAL_WIDTH=540' "$SRC_UNIT" || fail "unit sem largura interna"
grep -q 'LIVE_INFINITA_RENDER_INTERNAL_HEIGHT=960' "$SRC_UNIT" || fail "unit sem altura interna"

install -d -m 0700 "$BACKUP"
cp -a "$DST_RENDERER" "$BACKUP/headless_renderer.py"
cp -a "$DST_UNIT" "$BACKUP/live-infinita-renderer.service"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AE_ROLLBACK rc=$rc" >&2
    cp -a "$BACKUP/headless_renderer.py" "$DST_RENDERER" || true
    cp -a "$BACKUP/live-infinita-renderer.service" "$DST_UNIT" || true
    systemctl daemon-reload || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ae: source validation =="
"$PY" "$REPO/tests/test_headless_renderer.py"
"$PY" -m py_compile "$SRC_RENDERER"

echo "== 008ae: install renderer =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_RENDERER" "$DST_RENDERER"
install -o root -g root -m 0644 "$SRC_UNIT" "$DST_UNIT"
"$PY" -m py_compile "$DST_RENDERER"
systemctl daemon-reload
systemd-analyze verify "$DST_UNIT"

before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ae-renderer-journal.log
rm -f "$journal_probe"

echo "== 008ae: restart scaled renderer =="
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 60); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq '"render_width": 540' "$STATUS"        && grep -Fq '"render_height": 960' "$STATUS"        && grep -Fq '"output_width": 720' "$STATUS"        && grep -Fq '"output_height": 1280' "$STATUS"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done

if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer escalado não confirmou resolução + world feed"
fi

pgrep -af 'Xvfb :99 -screen 0 540x960x24' >/tmp/live-008ae-xvfb.txt || fail "Xvfb não usa 540x960"
pgrep -af -- '--resolution 540x960 res://world_map_preview.tscn' >/tmp/live-008ae-godot.txt || fail "Godot não usa 540x960"
pgrep -af 'ffmpeg.*-video_size 540x960.*scale=720:1280:flags=fast_bilinear' >/tmp/live-008ae-ffmpeg.txt || fail "ffmpeg não escala 540x960 -> 720x1280"

verified_mtime="$(stat -c %Y "$STATUS")"
sleep 10
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após escala interna"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer parou"

echo "== 008ae: final state =="
cat "$STATUS"
cat /tmp/live-008ae-xvfb.txt
cat /tmp/live-008ae-godot.txt
cat /tmp/live-008ae-ffmpeg.txt
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/tmp/live-008ae-runtime-health.json
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet "$SERVICE"
df -h /

SUCCESS=1
echo "INTERNAL_RENDER_SCALE_008AE_OK"
