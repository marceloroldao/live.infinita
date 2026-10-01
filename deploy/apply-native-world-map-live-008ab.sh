#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
SRC_RENDERER="$REPO/apps/headless-renderer/headless_renderer.py"
SRC_PROJECT="$REPO/apps/renderer-godot"
DST_PROJECT=/opt/live.infinita/apps/renderer-godot
SRC_WORLD="$SRC_PROJECT/world_map_preview.gd"
SRC_UNIT="$REPO/deploy/live-infinita-renderer.service"
DST_RENDERER=/opt/live.infinita/apps/headless-renderer/headless_renderer.py
DST_WORLD="$DST_PROJECT/world_map_preview.gd"
DST_UNIT=/etc/systemd/system/live-infinita-renderer.service
STATUS=/var/lib/live-infinita/render-runtime-status.json
SERVICE=live-infinita-renderer.service
EXPECTED_SCENE=res://world_map_preview.tscn
BACKUP=/var/backups/live-infinita/008ab-$(date -u +%Y%m%dT%H%M%SZ)
WORLD_FILES=(
  world_map_preview.tscn
  world_map_preview.gd
  world_map_live_feed.gd
  world_map_live_visual.gd
  world_map_cognitive_terrain.gd
  world_map_hud.gd
  world_map_local_motion.gd
  world_map_traversability.gd
  world_map_layout.gd
  world_map_features.gd
  world_map_001.json
  nature_asset_catalog.gd
)

fail() { echo "008AB_FAIL: $*" >&2; exit 2; }

[[ $EUID -eq 0 ]] || fail "execute com sudo"
[[ -x $PY ]] || fail "Python da Live ausente"
[[ -x $ENGINE ]] || fail "Godot engine ausente"
command -v rsync >/dev/null 2>&1 || fail "rsync ausente"
for path in "$SRC_RENDERER" "$SRC_WORLD" "$SRC_UNIT" "$DST_RENDERER" "$DST_WORLD" "$DST_UNIT"; do
  [[ -f $path ]] || fail "arquivo ausente: $path"
done
for name in "${WORLD_FILES[@]}"; do
  [[ -f "$SRC_PROJECT/$name" ]] || fail "pacote 3D ausente: $name"
done
[[ -d "$DST_PROJECT/assets/quaternius" ]] || fail "assets Quaternius instalados ausentes"
[[ -d "$DST_PROJECT/.godot/imported" ]] || fail "cache de import Godot ausente"
grep -q 'LIVE_INFINITA_RENDER_SCENE' "$SRC_RENDERER" || fail "renderer sem seleção de cena"
grep -q "Environment=LIVE_INFINITA_RENDER_SCENE=$EXPECTED_SCENE" "$SRC_UNIT" || fail "unit sem cena 3D"
grep -q 'func _configure_native_fps_governor' "$SRC_WORLD" || fail "mundo 3D sem governor nativo"

install -d -m 0700 "$BACKUP"
cp -a "$DST_RENDERER" "$BACKUP/headless_renderer.py"
cp -a "$DST_UNIT" "$BACKUP/live-infinita-renderer.service"
cp -a "$DST_PROJECT" "$BACKUP/renderer-godot"

SUCCESS=0
rollback() {
  rc=$?
  trap - EXIT
  if [[ $SUCCESS -eq 0 ]]; then
    echo "008AB_ROLLBACK rc=$rc" >&2
    systemctl stop "$SERVICE" || true
    cp -a "$BACKUP/headless_renderer.py" "$DST_RENDERER" || true
    rsync -a --delete "$BACKUP/renderer-godot/" "$DST_PROJECT/" || true
    cp -a "$BACKUP/live-infinita-renderer.service" "$DST_UNIT" || true
    systemctl daemon-reload || true
    systemctl restart "$SERVICE" || true
  fi
  exit "$rc"
}
trap rollback EXIT

echo "== 008ab: source validation =="
"$PY" -m py_compile "$SRC_RENDERER"
"$PY" "$REPO/tests/test_headless_renderer.py"

echo "== 008ab: install renderer =="
install -o liveinfinita -g liveinfinita -m 0664 "$SRC_RENDERER" "$DST_RENDERER"
for name in "${WORLD_FILES[@]}"; do
  install -o liveinfinita -g liveinfinita -m 0664 "$SRC_PROJECT/$name" "$DST_PROJECT/$name"
done
[[ -f "$DST_PROJECT/world_map_preview.tscn" ]] || fail "cena 3D não foi instalada"
install -o root -g root -m 0644 "$SRC_UNIT" "$DST_UNIT"
"$PY" -m py_compile "$DST_RENDERER"
grep -q 'LIVE_INFINITA_RENDER_SCENE' "$DST_RENDERER" || fail "renderer instalado sem seleção de cena"
grep -q 'func _configure_native_fps_governor' "$DST_WORLD" || fail "mundo instalado sem governor"
systemctl daemon-reload
systemd-analyze verify "$DST_UNIT"

echo "== 008ab: restart native renderer in 3D =="
before_mtime=0
if [[ -f "$STATUS" ]]; then
  before_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
fi
start_ts="$(date -u '+%Y-%m-%d %H:%M:%S')"
journal_probe=/tmp/live-008ab-renderer-journal.log
rm -f "$journal_probe"
systemctl restart "$SERVICE"
ready=0
for _ in $(seq 1 60); do
  if systemctl is-active --quiet "$SERVICE" && [[ -s "$STATUS" ]]; then
    current_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
    journalctl -u "$SERVICE" --since "$start_ts" --no-pager > "$journal_probe" || true
    if (( current_mtime > before_mtime ))        && grep -Fq "$EXPECTED_SCENE" "$STATUS"        && grep -Fq 'WORLD_MAP_PREVIEW_READY' "$journal_probe"        && grep -Fq 'WORLD_MAP_LIVE_BOUND' "$journal_probe"; then
      ready=1
      break
    fi
  fi
  sleep 1
done
if [[ "$ready" != "1" ]]; then
  systemctl status "$SERVICE" --no-pager -n 80 || true
  cat "$journal_probe" 2>/dev/null || true
  fail "renderer 3D não confirmou cena + world feed"
fi

echo "== 008ab: sustained 3D check =="
verified_mtime="$(stat -c %Y "$STATUS")"
sleep 12
systemctl is-active --quiet "$SERVICE" || fail "renderer caiu após iniciar 3D"
new_mtime="$(stat -c %Y "$STATUS" 2>/dev/null || echo 0)"
(( new_mtime > verified_mtime )) || fail "telemetria do renderer 3D parou"
grep -Fq "$EXPECTED_SCENE" "$STATUS" || fail "telemetria perdeu a cena 3D"
pgrep -af 'world_map_preview.tscn' > /tmp/live-008ab-godot-process.txt || fail "processo Godot 3D ausente"
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health > /tmp/live-008ab-runtime-health.json

echo "== 008ab: final state =="
cat "$STATUS"

SUCCESS=1
echo "NATIVE_WORLD_MAP_LIVE_008AB_OK"
