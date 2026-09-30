#!/usr/bin/env bash
# Root-only: export an exact Git snapshot and atomically publish Godot Web.
# Never run Godot against the installed native renderer project.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
WEB=/var/www/live-infinita-godot
BACKUP_BASE=/var/backups/live-infinita
GODOT=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PY=/opt/live.infinita/.venv/bin/python
NATIVE=live-infinita-renderer.service
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
BROADCASTER=live-infinita-broadcaster.service
URL=https://live.etbra.com.br/godot/build.json
fail(){ echo "FOREST_WEB_DEPLOY_BLOCKED $1" >&2; exit 2; }
[[ "$EUID" -eq 0 && $# -eq 1 && "$1" =~ ^[a-f0-9]{40}$ ]] || fail "root_or_commit"
SHA="$1"
exec 9>/run/lock/live-infinita-forest-web.lock
flock -n 9 || fail "deployment_in_progress"
[[ -x "$GODOT" && -x "$PY" && -d "$WEB" && ! -L "$WEB" && -f "$WEB/index.html" && -f "$WEB/build.json" ]] || fail "web_source_invalid"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" branch --show-current)" == main ]] || fail "checkout_not_main"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)" == "$SHA" &&
    "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse origin/main)" == "$SHA" ]] || fail "checkout_moved"
[[ -z "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain --untracked-files=no)" ]] || fail "dirty_checkout"
if systemctl is-active --quiet "$BROADCASTER"; then fail "external_broadcast_in_progress"; fi
[[ -z "$(find "$WEB" -type l -print -quit)" ]] || fail "public_web_symlink"
[[ -z "$(find "$WEB" -mindepth 1 -maxdepth 1 -type d ! -name nov-preview -print -quit)" ]] || fail "unknown_public_directory"
for unit in "$NATIVE" "$WORLD" "$API" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$unit" || fail "current_service_inactive"
done
declare -a pre_pid=()
for unit in "$NATIVE" "$WORLD" "$API" "$AUDIO" "$RELAY"; do
    pre_pid+=("$(systemctl show "$unit" -p MainPID --value)")
done
OLD_BUILD_SHA="$(sha256sum "$WEB/build.json" | cut -d' ' -f1)"
CURRENT_SHA="$("$PY" -c 'import json,sys;print(json.load(open(sys.argv[1]))["source_commit"])' "$WEB/build.json")"
if [[ "$CURRENT_SHA" == "$SHA" ]]; then
    echo "FOREST_WEB_ALREADY_CURRENT $SHA"
    exit 0
fi
nginx -t >/dev/null 2>&1 || fail "nginx_config"
WORK="$(mktemp -d /var/tmp/live-forest-web.XXXXXXXX)"
CANDIDATE="$(mktemp -d /var/www/.live-forest-web.XXXXXXXX)"
BACKUP="$(mktemp -d "$BACKUP_BASE/forest-web-001.XXXXXXXX")"
old_moved=0
cleanup(){
    rc=$?
    trap - EXIT INT TERM
    set +e
    if ((rc != 0 && old_moved == 1)); then
        echo "FOREST_WEB_ROLLBACK_STARTED" >&2
        if [[ -d "$WEB" && ! -L "$WEB" ]]; then
            mv -T -- "$WEB" "$BACKUP/failed-candidate" || rc=2
        fi
        if [[ ! -e "$WEB" && -d "$BACKUP/site" ]]; then
            mv -T -- "$BACKUP/site" "$WEB" || rc=2
        fi
        if [[ -f "$WEB/build.json" &&
            "$(sha256sum "$WEB/build.json" | cut -d' ' -f1)" == "$OLD_BUILD_SHA" ]]; then
            echo "FOREST_WEB_ROLLBACK_OK"
        else
            echo "FOREST_WEB_ROLLBACK_BLOCKED inspect_backup" >&2
            rc=2
        fi
    fi
    if [[ -d "$CANDIDATE" && ! -L "$CANDIDATE" ]]; then rm -rf -- "$CANDIDATE"; fi
    if [[ -d "$WORK" && ! -L "$WORK" ]]; then rm -rf -- "$WORK"; fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
echo "FOREST_WEB_SNAPSHOT_BEGIN sha=$SHA"
git -c safe.directory="$REPO" -C "$REPO" archive "$SHA" apps/renderer-godot | tar -xf - -C "$WORK" ||
    fail "git_snapshot_failed"
PROJECT="$WORK/apps/renderer-godot"
for path in project.godot export_presets.cfg main.tscn diorama.gd forest_preview.gd forest_preview.tscn; do
    [[ -s "$PROJECT/$path" && ! -L "$PROJECT/$path" ]] || fail "source_bundle_incomplete"
done
[[ -z "$(find "$PROJECT" -type l -print -quit)" ]] || fail "project_symlink"
grep -Fq 'run/main_scene="res://main.tscn"' "$PROJECT/project.godot" || fail "production_scene_changed"
grep -Fq "FOREST_TREE_COUNT := 17" "$PROJECT/diorama.gd" || fail "forest_missing"
echo "FOREST_WEB_SNAPSHOT_OK"
# Editor preimport and export run only in an isolated snapshot, never the native
# project. Low priority prevents optional export from starving the live world.
mkdir -p "$WORK/build"
GODOT_SILENCE_ROOT_WARNING=1 nice -n 15 "$GODOT" --headless --editor --quit --path "$PROJECT" > "$WORK/editor.log" 2>&1 ||
    fail "godot_import_failed"
if grep -Eiq 'SCRIPT ERROR:|Parser Error:|Failed to load script|^ERROR:' "$WORK/editor.log"; then
    echo "FOREST_WEB_GODOT_IMPORT_DIAGNOSTIC" >&2
    fail "godot_import_diagnostics"
fi
echo "FOREST_WEB_ASSETS_IMPORTED"
GODOT_SILENCE_ROOT_WARNING=1 nice -n 15 "$GODOT" --headless --path "$PROJECT" --export-release Web "$WORK/build/index.html" > "$WORK/export.log" 2>&1 ||
    fail "godot_export_failed"
if grep -Eiq 'SCRIPT ERROR:|Parser Error:|Failed to load script|^ERROR:' "$WORK/export.log"; then
    echo "FOREST_WEB_GODOT_EXPORT_DIAGNOSTIC" >&2
    fail "godot_export_diagnostics"
fi
for file in index.html index.js index.pck index.wasm; do
    [[ -s "$WORK/build/$file" ]] || fail "missing_export_artifact"
done
[[ "$(stat -c %s "$WORK/build/index.pck")" -gt 1000000 ]] || fail "export_package_too_small"
echo "FOREST_WEB_EXPORT_OK"
# Stage on the same filesystem as the site for rename(2) swaps.
cp -a -- "$WORK/build/." "$CANDIDATE/"
if [[ -d "$WEB/nov-preview" ]]; then
    cp -a -- "$WEB/nov-preview" "$CANDIDATE/nov-preview"
    cmp -s "$WEB/nov-preview/build.json" "$CANDIDATE/nov-preview/build.json" ||
        fail "nov_preview_not_preserved"
fi
"$PY" - "$CANDIDATE/build.json" "$SHA" <<'PY'
import json, pathlib, sys, datetime
path = pathlib.Path(sys.argv[1])
path.write_text(json.dumps({
    "source_commit": sys.argv[2],
    "built_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "project": "Live Infinita Showcase",
    "renderer": "godot-web",
    "engine": "Godot_v4.7.2-stable_linux.x86_64",
    "scenario": "forest-stage-001",
}, indent=2) + "\n", encoding="utf-8")
PY
chown -R www-data:www-data "$CANDIDATE"
find "$CANDIDATE" -type d -exec chmod 0755 {} +
find "$CANDIDATE" -type f -exec chmod 0644 {} +
echo "FOREST_WEB_CANDIDATE_READY"
# Existing site is retained as a versioned filesystem backup. Only static
# content switches; nginx configuration and all systemd services stay untouched.
mv -T -- "$WEB" "$BACKUP/site" || fail "old_site_backup_failed"
old_moved=1
mv -T -- "$CANDIDATE" "$WEB" || fail "candidate_promotion_failed"
CANDIDATE="$WORK/no-candidate"
# Validate through local nginx under the real hostname and independent files.
PUBLIC_SHA="$(curl --silent --show-error --fail --max-time 15 --resolve live.etbra.com.br:443:127.0.0.1 "$URL" | "$PY" -c 'import json,sys;print(json.load(sys.stdin)["source_commit"])')" ||
    fail "public_build_unavailable"
[[ "$PUBLIC_SHA" == "$SHA" ]] || fail "public_build_commit_mismatch"
for file in index.html index.js index.pck index.wasm; do
    code="$(curl --silent --show-error --output /dev/null --max-time 15 --resolve live.etbra.com.br:443:127.0.0.1 --write-out '%{http_code}' "https://live.etbra.com.br/godot/$file")" ||
        fail "public_artifact_unavailable"
    [[ "$code" == 200 || "$code" == 206 ]] || fail "public_artifact_http"
done
if [[ -d "$BACKUP/site/nov-preview" ]]; then
    cmp -s "$BACKUP/site/nov-preview/build.json" "$WEB/nov-preview/build.json" ||
        fail "nov_preview_changed"
fi
for i in "${!pre_pid[@]}"; do
    case "$i" in
        0) unit="$NATIVE";; 1) unit="$WORLD";; 2) unit="$API";;
        3) unit="$AUDIO";; 4) unit="$RELAY";;
    esac
    systemctl is-active --quiet "$unit" || fail "service_changed"
    [[ "$(systemctl show "$unit" -p MainPID --value)" == "${pre_pid[$i]}" ]] ||
        fail "service_restarted"
done
echo "FOREST_WEB_ATOMIC_PUBLISH_OK sha=$SHA previous=$CURRENT_SHA"
echo "FOREST_WEB_NATIVE_WORLD_AUDIO_UNCHANGED"
echo "FOREST_WEB_NOV_PREVIEW_PRESERVED"
echo "FOREST_WEB_BACKUP_PATH=$BACKUP/site"
echo "FOREST_WEB_URL=https://live.etbra.com.br/godot/"
