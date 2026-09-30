#!/usr/bin/env bash
# Root-only Visual 001: install ONLY three renderer-godot presentation files.
# On any failure restore previous files and, if restarted, the old renderer.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
TARGET=/opt/live.infinita/apps/renderer-godot
GODOT=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
RENDERER=live-infinita-renderer.service
BROADCASTER=live-infinita-broadcaster.service
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
FILES=(diorama.gd forest_preview.gd forest_preview.tscn)
fail(){ echo "FOREST001_DEPLOY_BLOCKED: $1" >&2; exit 2; }
[[ "$EUID" == 0 && $# == 1 && "$1" =~ ^[0-9a-f]{40}$ ]] || fail "root_or_sha"
SHA="$1"
exec 9>/run/lock/live-infinita-forest-visual.lock
flock -n 9 || fail "deploy_already_running"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)" == "$SHA" ]] ||
    fail "checkout_changed"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse origin/main)" == "$SHA" ]] ||
    fail "checkout_not_current"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" branch --show-current)" == main ]] ||
    fail "not_main"
[[ -z "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "dirty_checkout"
[[ -x "$GODOT" && -d "$TARGET" && -f "$TARGET/diorama.gd" &&
    ! -L "$TARGET" && ! -L "$TARGET/diorama.gd" ]] || fail "renderer_paths_invalid"
for svc in "$RENDERER" "$WORLD" "$API" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "service_not_active"
done
if systemctl is-active --quiet "$BROADCASTER"; then
    fail "broadcast_active_no_visual_restart"
fi
snapshot_pid(){
    systemctl show "$1" --property=MainPID --value
}
world_pid="$(snapshot_pid "$WORLD")"
api_pid="$(snapshot_pid "$API")"
audio_pid="$(snapshot_pid "$AUDIO")"
relay_pid="$(snapshot_pid "$RELAY")"
old_renderer_pid="$(snapshot_pid "$RENDERER")"

STAGE="$(mktemp -d /tmp/live-forest-visual.XXXXXXXX)"
BACKUP="$(mktemp -d /var/backups/live-infinita/forest-stage-001.XXXXXXXX)"
applied=0
restarted=0
had_preview_gd=0
had_preview_tscn=0
cleaned=0
cleanup(){
    rc=$?
    trap - EXIT INT TERM
    set +e
    if [[ "$applied" == 1 && "$rc" != 0 ]]; then
        echo "FOREST001_ROLLBACK_STARTED" >&2
        cp -a -- "$BACKUP/diorama.gd" "$TARGET/diorama.gd"
        if [[ "$had_preview_gd" == 1 ]]; then
            cp -a -- "$BACKUP/forest_preview.gd" "$TARGET/forest_preview.gd"
        else
            rm -f -- "$TARGET/forest_preview.gd"
        fi
        if [[ "$had_preview_tscn" == 1 ]]; then
            cp -a -- "$BACKUP/forest_preview.tscn" "$TARGET/forest_preview.tscn"
        else
            rm -f -- "$TARGET/forest_preview.tscn"
        fi
        if [[ "$restarted" == 1 ]]; then
            systemctl restart "$RENDERER" >/dev/null 2>&1
        fi
        if cmp -s "$BACKUP/diorama.gd" "$TARGET/diorama.gd" &&
            systemctl is-active --quiet "$RENDERER"; then
            echo "FOREST001_ROLLBACK_OK"
        else
            echo "FOREST001_ROLLBACK_BLOCKED manual_check" >&2
            rc=2
        fi
    fi
    rm -rf -- "$STAGE"
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for file in "${FILES[@]}"; do
    [[ ! -L "$TARGET/$file" ]] || fail "target_symlink"
    git -c safe.directory="$REPO" -C "$REPO" show \
        "$SHA:apps/renderer-godot/$file" >"$STAGE/$file" ||
        fail "git_file_unavailable"
    [[ -s "$STAGE/$file" ]] || fail "empty_file"
done
if cmp -s "$STAGE/diorama.gd" "$TARGET/diorama.gd" &&
    test -f "$TARGET/forest_preview.gd" &&
    test -f "$TARGET/forest_preview.tscn" &&
    cmp -s "$STAGE/forest_preview.gd" "$TARGET/forest_preview.gd" &&
    cmp -s "$STAGE/forest_preview.tscn" "$TARGET/forest_preview.tscn"; then
    echo "FOREST001_ALREADY_DEPLOYED"
    exit 0
fi

cp -a -- "$TARGET/diorama.gd" "$BACKUP/diorama.gd"
if [[ -e "$TARGET/forest_preview.gd" ]]; then
    [[ -f "$TARGET/forest_preview.gd" ]] || fail "preview_source_invalid"
    cp -a -- "$TARGET/forest_preview.gd" "$BACKUP/forest_preview.gd"
    had_preview_gd=1
fi
if [[ -e "$TARGET/forest_preview.tscn" ]]; then
    [[ -f "$TARGET/forest_preview.tscn" ]] || fail "preview_scene_invalid"
    cp -a -- "$TARGET/forest_preview.tscn" "$BACKUP/forest_preview.tscn"
    had_preview_tscn=1
fi
echo "FOREST001_BACKUP_READY $BACKUP"
applied=1
for file in "${FILES[@]}"; do
    install -o liveinfinita -g liveinfinita -m 0644 \
        "$STAGE/$file" "$TARGET/$file" || fail "install_failed"
    cmp -s -- "$STAGE/$file" "$TARGET/$file" || fail "installed_bytes_mismatch"
done
echo "FOREST001_SOURCE_INSTALLED"

# Run only parser checks, not a full editor import in the running service's
# project tree; the 46 MB optional glTF pack does not enter the live main scene.
# Parse from a root-private, asset-free project; never run root Godot in the
# live project tree, which would risk changing the service owner's import cache.
git -c safe.directory="$REPO" -C "$REPO" show \
    "$SHA:apps/renderer-godot/project.godot" >"$STAGE/project.godot" ||
    fail "project_manifest_unavailable"
GODOT_SILENCE_ROOT_WARNING=1 "$GODOT" --headless --path "$STAGE" \
    --check-only --script diorama.gd >"$STAGE/godot-parse.log" 2>&1 ||
    fail "godot_parse_failed"
if grep -Eq 'SCRIPT ERROR|Parser Error|^ERROR:' "$STAGE/godot-parse.log"; then
    fail "godot_parse_diagnostic"
fi
echo "FOREST001_RENDERER_PARSE_OK"

started_at="$(date --utc '+%Y-%m-%d %H:%M:%S')"
restarted=1
systemctl restart "$RENDERER" || fail "renderer_restart_failed"
ready=0
new_renderer_pid=0
for ((i=0; i<25; i++)); do
    new_renderer_pid="$(snapshot_pid "$RENDERER")"
    if systemctl is-active --quiet "$RENDERER" &&
        [[ "$new_renderer_pid" =~ ^[0-9]+$ &&
            "$new_renderer_pid" -gt 1 &&
            "$new_renderer_pid" != "$old_renderer_pid" ]] &&
        journalctl -u "$RENDERER" --since "$started_at" --no-pager \
            | grep -F '[render] native fast sky enabled' >/dev/null; then
        ready=1
        break
    fi
    sleep 1
done
[[ "$ready" == 1 ]] || fail "renderer_not_ready"
sleep 8
systemctl is-active --quiet "$RENDERER" || fail "renderer_inactive_after_start"
[[ "$(snapshot_pid "$RENDERER")" == "$new_renderer_pid" ]] ||
    fail "renderer_unexpected_restart"
if journalctl -u "$RENDERER" --since "$started_at" --no-pager \
    | grep -Eq 'SCRIPT ERROR|Parser Error|Shader compilation failed'; then
    fail "renderer_script_error"
fi
for pair in "$WORLD:$world_pid" "$API:$api_pid" "$AUDIO:$audio_pid" "$RELAY:$relay_pid"; do
    IFS=: read -r svc prior <<<"$pair"
    systemctl is-active --quiet "$svc" || fail "other_service_down"
    [[ "$(snapshot_pid "$svc")" == "$prior" ]] || fail "other_service_restarted"
done
echo "FOREST001_NATIVE_DEPLOY_OK renderer_pid=$new_renderer_pid"
echo "FOREST001_WORLD_AUDIO_UNCHANGED"
echo "FOREST001_WEB_EXPORT_NOT_CHANGED"
echo "FOREST001_BACKUP_PATH=$BACKUP"
