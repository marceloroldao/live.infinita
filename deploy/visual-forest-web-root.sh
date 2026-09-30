#!/usr/bin/env bash
# Root-only: immutable Git archive -> isolated Godot import/export -> Web directory
# replacement with preserved /nov-preview and an on-disk rollback copy.
# NEVER clear the live project's .godot, restart services or touch World State.
set -Eeuo pipefail
umask 077

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita/apps/renderer-godot
GODOT=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
WEB=/var/www/live-infinita-godot
WEB_PARENT=/var/www
BACKUP_PARENT=/var/backups/live-infinita
BROADCASTER=live-infinita-broadcaster.service
SERVICES=(live-infinita-renderer.service live-infinita-autonomous-world.service live-infinita.service live-infinita-audio.service live-infinita-audio-web.service)
fail(){ echo "FOREST_WEB_BLOCKED: $1" >&2; exit 2; }

[[ "$EUID" -eq 0 && $# -eq 1 && "$1" =~ ^[a-f0-9]{40}$ ]] ||
    fail "root_or_sha"
SHA="$1"
exec 9>/run/lock/live-infinita-forest-web.lock
flock -n 9 || fail "concurrent_web_release"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)" == "$SHA" &&
   "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse origin/main)" == "$SHA" &&
   "$(git -c safe.directory="$REPO" -C "$REPO" branch --show-current)" == main ]] ||
    fail "commit_not_current_main"
[[ -z "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "tracked_checkout_modified"
[[ -x "$GODOT" && -f "$INSTALL/diorama.gd" &&
   -d "$WEB" && ! -L "$WEB" && -s "$WEB/index.html" &&
   -s "$WEB/index.pck" && -s "$WEB/index.wasm" &&
   -s "$WEB/build.json" && ! -L "$WEB/build.json" ]] ||
    fail "existing_web_or_runtime_invalid"
[[ -d "$BACKUP_PARENT" && ! -L "$BACKUP_PARENT" &&
   -d "$WEB_PARENT" && ! -L "$WEB_PARENT" ]] ||
    fail "release_parent_invalid"
if systemctl is-active --quiet "$BROADCASTER"; then
    fail "external_broadcast_active"
fi
declare -A PIDS=()
for svc in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$svc" || fail "existing_service_inactive"
    PIDS["$svc"]="$(systemctl show "$svc" -p MainPID --value)"
    [[ "${PIDS[$svc]}" =~ ^[0-9]+$ && "${PIDS[$svc]}" -gt 1 ]] ||
        fail "service_pid_invalid"
done
before_build="$(sha256sum "$WEB/build.json" | cut -d' ' -f1)"
WORK="$(mktemp -d /var/tmp/live-forest-web.XXXXXXXX)"
NEXT="$(mktemp -d "$WEB_PARENT/.live-forest-next.XXXXXXXX")"
BACKUP="$(mktemp -d "$BACKUP_PARENT/forest-web-001.XXXXXXXX")"
old_moved=0
published=0
cleanup(){
    rc=$?
    trap - EXIT INT TERM
    set +e
    if [[ "$rc" -ne 0 && "$old_moved" == 1 ]]; then
        echo "FOREST_WEB_ROLLBACK_STARTED" >&2
        if [[ "$published" == 1 && -d "$WEB" && ! -L "$WEB" ]]; then
            mv -- "$WEB" "$BACKUP/failed-release"
        fi
        if [[ -d "$BACKUP/previous" && ! -e "$WEB" && ! -L "$WEB" ]]; then
            mv -- "$BACKUP/previous" "$WEB"
        fi
        if [[ -d "$WEB" && ! -L "$WEB" &&
              "$(sha256sum "$WEB/build.json" 2>/dev/null | cut -d' ' -f1)" == "$before_build" ]]; then
            echo "FOREST_WEB_ROLLBACK_OK"
        else
            echo "FOREST_WEB_ROLLBACK_BLOCKED manual_inspection_required" >&2
            rc=2
        fi
    fi
    [[ ! -d "$WORK" ]] || rm -rf -- "$WORK"
    [[ ! -d "$NEXT" ]] || rm -rf -- "$NEXT"
    # Successful releases retain /var/backups/.../previous for manual rollback.
    # Failed releases retain their backup/failed-release for diagnosis.
    if [[ "$old_moved" == 0 && -d "$BACKUP" ]]; then
        rmdir "$BACKUP" >/dev/null 2>&1 || true
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

echo "FOREST_WEB_SOURCE_SHA=$SHA"
# Exact tracked Git objects, no local untracked imports and no access to the
# native project's .godot while it is rendering.
git -c safe.directory="$REPO" -C "$REPO" archive --format=tar "$SHA" apps/renderer-godot |
    tar -xf - -C "$WORK" || fail "archive_source_failed"
PROJECT="$WORK/apps/renderer-godot"
BUILD="$WORK/export"
mkdir -p "$BUILD"
[[ -s "$PROJECT/main.tscn" && -s "$PROJECT/project.godot" &&
   -s "$PROJECT/export_presets.cfg" && -s "$PROJECT/diorama.gd" ]] ||
    fail "staged_project_incomplete"
cmp -s "$PROJECT/diorama.gd" "$INSTALL/diorama.gd" ||
    fail "native_forest_not_deployed"
grep -Fq 'run/main_scene="res://main.tscn"' "$PROJECT/project.godot" ||
    fail "wrong_main_scene"
[[ ! -d "$PROJECT/.godot" ]] || fail "staging_contains_import_cache"
echo "FOREST_WEB_ISOLATED_SOURCE_OK"

# These two expensive steps are reduced priority on the 2-core server.
# Do not run root Godot against /opt/live.infinita/apps/renderer-godot.
if ! timeout 600 nice -n 19 env GODOT_SILENCE_ROOT_WARNING=1 "$GODOT" \
    --headless --editor --quit --path "$PROJECT" >"$WORK/import.log" 2>&1; then
    echo "FOREST_WEB_IMPORT_FAILED" >&2
    tail -n 25 "$WORK/import.log" >&2
    fail "isolated_import_failed"
fi
if grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/import.log"; then
    grep -Ei 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/import.log" | tail -n 14 >&2
    fail "isolated_import_diagnostics"
fi
echo "FOREST_WEB_IMPORT_OK"
if ! timeout 600 nice -n 19 env GODOT_SILENCE_ROOT_WARNING=1 "$GODOT" \
    --headless --path "$PROJECT" --export-release Web "$BUILD/index.html" \
    >"$WORK/export.log" 2>&1; then
    tail -n 25 "$WORK/export.log" >&2
    fail "isolated_export_failed"
fi
if grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/export.log"; then
    grep -Ei 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/export.log" | tail -n 14 >&2
    fail "isolated_export_diagnostics"
fi
python3 - "$BUILD" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1])
expected=("index.html","index.js","index.pck","index.wasm")
if any(not (root/name).is_file() or (root/name).stat().st_size < 100 for name in expected):
    raise SystemExit("FOREST_WEB_EXPORT_INCOMPLETE")
if (root/"index.pck").stat().st_size < 100_000:
    raise SystemExit("FOREST_WEB_PCK_INCOMPLETE")
print("FOREST_WEB_ARTIFACT_OK")
PY
# Build metadata is written only to the staged release.
python3 - "$BUILD/build.json" "$SHA" "$(basename "$GODOT")" <<'PY'
import json,sys
from datetime import datetime,timezone
from pathlib import Path
Path(sys.argv[1]).write_text(json.dumps({
    "source_commit":sys.argv[2],
    "built_at":datetime.now(timezone.utc).isoformat(),
    "project":"Live Infinita Showcase",
    "renderer":"godot-web",
    "engine":sys.argv[3],
    "visual_stage":"forest-001",
},sort_keys=True,indent=2)+"\n")
PY

# Preserve separate Nov 3D preview without deleting or rebuilding it.
cp -a -- "$BUILD/." "$NEXT/"
if [[ -e "$WEB/nov-preview" || -L "$WEB/nov-preview" ]]; then
    [[ -d "$WEB/nov-preview" && ! -L "$WEB/nov-preview" &&
       -s "$WEB/nov-preview/index.html" ]] || fail "nov_preview_invalid"
    cp -a -- "$WEB/nov-preview" "$NEXT/nov-preview"
    echo "FOREST_WEB_NOV_PREVIEW_PRESERVED"
fi
chown -R www-data:www-data "$NEXT"
find "$NEXT" -type d -exec chmod 0755 {} +
find "$NEXT" -type f -exec chmod 0644 {} +
[[ -s "$NEXT/index.html" && -s "$NEXT/index.pck" &&
   -s "$NEXT/index.wasm" && -s "$NEXT/build.json" ]] || fail "stage_incomplete"
nginx -t >"$WORK/nginx-verify.log" 2>&1 || fail "nginx_config_invalid"
for svc in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$svc" &&
        [[ "$(systemctl show "$svc" -p MainPID --value)" == "${PIDS[$svc]}" ]] ||
        fail "existing_service_changed_during_build"
done
if systemctl is-active --quiet "$BROADCASTER"; then
    fail "external_broadcast_became_active"
fi
echo "FOREST_WEB_RELEASE_READY"

# Rename old directory into a protected backup; publish next directory by
# same-filesystem rename. There is a short URL gap between the two renames.
mv -- "$WEB" "$BACKUP/previous" || fail "old_release_backup_failed"
old_moved=1
mv -- "$NEXT" "$WEB" || fail "new_release_publication_failed"
published=1
echo "FOREST_WEB_PUBLICATION_SWITCHED"

# Verify Nginx serves precisely this commit and both export payloads.
curl -fsS -m 12 -H 'Host: live.etbra.com.br' \
    http://127.0.0.1/godot/build.json >"$WORK/served.json" ||
    fail "published_manifest_http_failed"
python3 - "$WORK/served.json" "$SHA" <<'PY'
import json,sys
from pathlib import Path
item=json.loads(Path(sys.argv[1]).read_text())
if item.get("source_commit") != sys.argv[2] or item.get("visual_stage") != "forest-001":
    raise SystemExit("FOREST_WEB_PUBLISHED_COMMIT_MISMATCH")
PY
for resource in index.html index.js index.pck index.wasm; do
    code="$(curl -sS -m 12 -o /dev/null -w '%{http_code}' \
        -H 'Host: live.etbra.com.br' -I "http://127.0.0.1/godot/$resource")"
    [[ "$code" == 200 ]] || fail "published_resource_http_failed"
done
if [[ -d "$WEB/nov-preview" ]]; then
    [[ "$(curl -sS -m 12 -o /dev/null -w '%{http_code}' \
        -H 'Host: live.etbra.com.br' -I http://127.0.0.1/godot/nov-preview/index.html)" == 200 ]] ||
        fail "nov_preview_http_failed"
fi
for svc in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$svc" &&
        [[ "$(systemctl show "$svc" -p MainPID --value)" == "${PIDS[$svc]}" ]] ||
        fail "service_changed_after_web_release"
done
[[ "$(curl -sS -m 8 -o /dev/null -w '%{http_code}' \
    http://127.0.0.1:8080/api/health)" == 200 ]] ||
    fail "world_health_changed"
echo "FOREST_WEB_PUBLISHED_OK source_commit=$SHA"
echo "FOREST_WEB_WORLD_RENDERER_AUDIO_UNCHANGED"
echo "FOREST_WEB_BACKUP_PATH=$BACKUP/previous"
