#!/usr/bin/env bash
# Root-only Web deployment. Builds exact Git source in /var/tmp and atomically
# replaces ONLY /godot/. No access to private world/memory and no service restarts.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
WEB=/var/www/live-infinita-godot
GODOT=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
SERVICES=(live-infinita-renderer.service live-infinita-autonomous-world.service
          live-infinita.service live-infinita-audio.service
          live-infinita-audio-web.service live-infinita-memoria-local.service)
fail(){ echo "FOREST001_WEB_BLOCKED: $1" >&2; exit 2; }
[[ "$EUID" -eq 0 && $# -eq 1 && "$1" =~ ^[0-9a-f]{40}$ ]] ||
    fail "root_or_commit"
SHA="$1"
exec 9>/run/lock/live-infinita-forest-web.lock
flock -n 9 || fail "deploy_already_running"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)" == "$SHA" &&
    "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse origin/main)" == "$SHA" &&
    "$(git -c safe.directory="$REPO" -C "$REPO" branch --show-current)" == main &&
    -z "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "checkout_not_clean_main"
[[ -x "$GODOT" && -d "$WEB" && ! -L "$WEB" &&
    -s "$WEB/index.html" && -s "$WEB/index.pck" &&
    -s "$WEB/build.json" && -s "$WEB/nov-preview/index.pck" &&
    -s "$WEB/nov-preview/build.json" && ! -L "$WEB/nov-preview" ]] ||
    fail "web_or_nov_preview_missing"
[[ -s /opt/live.infinita/apps/renderer-godot/diorama.gd ]] ||
    fail "native_renderer_missing"
cmp -s "$REPO/apps/renderer-godot/diorama.gd" \
       /opt/live.infinita/apps/renderer-godot/diorama.gd ||
    fail "native_forest_not_deployed"
for svc in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$svc" || fail "existing_service_inactive"
done
declare -A BEFORE_PIDS=()
for svc in "${SERVICES[@]}"; do
    BEFORE_PIDS["$svc"]="$(systemctl show "$svc" -p MainPID --value)"
done
current_sha="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("source_commit",""))' "$WEB/build.json")"
if [[ "$current_sha" == "$SHA" ]] &&
   grep -Fq '"forest_stage": "visual-001"' "$WEB/build.json"; then
    echo "FOREST001_WEB_ALREADY_CURRENT source_commit=$SHA"
    exit 0
fi
nginx -t >/dev/null 2>&1 || fail "nginx_config"
test "$(df -Pk /var/www | awk 'NR==2 {print $4}')" -gt 1200000 ||
    fail "disk_budget"

WORK=""
STAGE=""
BACKUP=""
saved_old=0
old_build_digest="$(sha256sum "$WEB/build.json" | cut -d' ' -f1)"
old_nov_digest="$(sha256sum "$WEB/nov-preview/index.pck" | cut -d' ' -f1)"
cleanup(){
    rc=$?
    trap - EXIT INT TERM
    set +e
    if ((rc != 0 && saved_old)); then
        echo "FOREST001_WEB_ROLLBACK_STARTED" >&2
        if [[ -d "$WEB" && -n "$BACKUP" ]]; then
            mv -T -- "$WEB" "$BACKUP/failed-new" 2>/dev/null
        fi
        if [[ -d "$BACKUP/site" ]]; then
            mv -T -- "$BACKUP/site" "$WEB" 2>/dev/null
        fi
        if [[ -s "$WEB/build.json" &&
              "$(sha256sum "$WEB/build.json" | cut -d' ' -f1)" == "$old_build_digest" &&
              -s "$WEB/nov-preview/index.pck" &&
              "$(sha256sum "$WEB/nov-preview/index.pck" | cut -d' ' -f1)" == "$old_nov_digest" ]]; then
            echo "FOREST001_WEB_ROLLBACK_OK"
        else
            echo "FOREST001_WEB_ROLLBACK_BLOCKED manual_restore_from_backup" >&2
            rc=2
        fi
    fi
    if [[ -n "$STAGE" && -d "$STAGE" ]]; then
        rm -rf -- "$STAGE"
    fi
    if [[ -n "$WORK" && -d "$WORK" ]]; then
        rm -rf -- "$WORK"
    fi
    if ((saved_old == 0)) && [[ -n "$BACKUP" && -d "$BACKUP" ]]; then
        rmdir -- "$BACKUP" 2>/dev/null || true
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# /var/tmp is disk-backed, unlike the VM's nearly full tmpfs /tmp.
WORK="$(mktemp -d /var/tmp/live-forest-web-project.XXXXXXXX)"
STAGE="$(mktemp -d /var/www/.live-infinita-godot.stage.XXXXXXXX)"
BACKUP="$(mktemp -d /var/www/.live-infinita-godot.backup.XXXXXXXX)"
git -c safe.directory="$REPO" -C "$REPO" archive "$SHA" apps/renderer-godot |
    tar -x -C "$WORK" || fail "exact_git_archive_failed"
PROJECT="$WORK/apps/renderer-godot"
[[ -s "$PROJECT/project.godot" && -s "$PROJECT/export_presets.cfg" &&
    -s "$PROJECT/main.tscn" && -s "$PROJECT/diorama.gd" &&
    -s "$PROJECT/forest_preview.tscn" ]] ||
    fail "public_project_incomplete"
[[ -z "$(find "$PROJECT" -type l -print -quit)" ]] ||
    fail "project_symlinks"
cmp -s "$PROJECT/diorama.gd" /opt/live.infinita/apps/renderer-godot/diorama.gd ||
    fail "native_and_web_forest_differ"
grep -Fq 'run/main_scene="res://main.tscn"' "$PROJECT/project.godot" ||
    fail "main_scene_changed"
echo "FOREST001_WEB_SNAPSHOT_READY commit=$SHA"

# Import + export only this private project. Lower scheduling priority to
# keep the 12–15 FPS native server renderer responsive without a GPU.
set +e
GODOT_SILENCE_ROOT_WARNING=1 timeout 720 nice -n 15 ionice -c 3 \
    "$GODOT" --headless --editor --quit --path "$PROJECT" >"$WORK/import.log" 2>&1
import_rc=$?
set -e
if ((import_rc != 0)) ||
   grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/import.log"; then
    echo "FOREST001_WEB_IMPORT_BLOCKED code=$import_rc" >&2
    grep -E 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/import.log" | tail -8 >&2 || true
    fail "private_import_failed"
fi
echo "FOREST001_WEB_IMPORT_OK"

set +e
GODOT_SILENCE_ROOT_WARNING=1 timeout 420 nice -n 15 ionice -c 3 \
    "$GODOT" --headless --path "$PROJECT" --export-release Web \
    "$STAGE/index.html" >"$WORK/export.log" 2>&1
export_rc=$?
set -e
if ((export_rc != 0)) ||
   grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/export.log"; then
    echo "FOREST001_WEB_EXPORT_BLOCKED code=$export_rc" >&2
    grep -E 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "$WORK/export.log" | tail -8 >&2 || true
    fail "private_export_failed"
fi
[[ -s "$STAGE/index.html" && -s "$STAGE/index.js" &&
    -s "$STAGE/index.wasm" && -s "$STAGE/index.pck" ]] ||
    fail "export_files_missing"
(( $(stat -c %s "$STAGE/index.pck") > 1000000 )) ||
    fail "export_pack_too_small"
echo "FOREST001_WEB_EXPORT_OK"

# Preserve the independent Nov preview byte for byte, not an extra export.
cp -a -- "$WEB/nov-preview" "$STAGE/nov-preview" ||
    fail "preserve_nov_preview"
[[ "$(sha256sum "$STAGE/nov-preview/index.pck" | cut -d' ' -f1)" == "$old_nov_digest" ]] ||
    fail "nov_preview_hash_changed"
cmp -s "$STAGE/nov-preview/build.json" "$WEB/nov-preview/build.json" ||
    fail "nov_preview_metadata_changed"
python3 - "$STAGE/build.json" "$SHA" <<'PY'
import json, pathlib, sys
path, sha = pathlib.Path(sys.argv[1]), sys.argv[2]
path.write_text(json.dumps({
    "source_commit": sha,
    "forest_stage": "visual-001",
    "built_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
    "project": "Live Infinita Showcase",
    "renderer": "godot-web",
    "engine": "Godot_v4.7.2-stable_linux.x86_64",
}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
chown -R www-data:www-data "$STAGE"
find "$STAGE" -type d -exec chmod 0755 {} +
find "$STAGE" -type f -exec chmod 0644 {} +
[[ -s "$STAGE/build.json" ]] || fail "build_metadata_missing"

# Two same-filesystem renames minimize the publication gap (brief 404 is
# possible between them); the old site stays in a private rollback directory.
mv -T -- "$WEB" "$BACKUP/site" || fail "save_previous_site"
saved_old=1
mv -T -- "$STAGE" "$WEB" || fail "publish_rename"
echo "FOREST001_WEB_RENAME_SWAP_OK"

# Validate the actual local nginx vhost/alias and original Nov preview.
url=https://live.etbra.com.br/godot
live_metadata="$(curl -fsS --max-time 12 --resolve live.etbra.com.br:443:127.0.0.1 \
    "$url/build.json?forest=$SHA")" || fail "public_build_unavailable"
[[ "$live_metadata" == "$(cat "$WEB/build.json")" ]] ||
    fail "public_build_mismatch"
live_pack_bytes="$(curl -fsSI --max-time 12 --resolve live.etbra.com.br:443:127.0.0.1 \
    "$url/index.pck?forest=$SHA" | tr -d '\r' | awk 'tolower($1)=="content-length:" {print $2; exit}')" ||
    fail "public_pack_unavailable"
[[ "$live_pack_bytes" == "$(stat -c %s "$WEB/index.pck")" ]] ||
    fail "public_pack_mismatch"
curl -fsS --max-time 12 --resolve live.etbra.com.br:443:127.0.0.1 \
    "$url/nov-preview/build.json?preserved=$SHA" > "$WORK/nov-actual.json" ||
    fail "public_nov_preview_unavailable"
cmp -s "$WORK/nov-actual.json" "$BACKUP/site/nov-preview/build.json" ||
    fail "public_nov_preview_changed"
for svc in "${SERVICES[@]}"; do
    systemctl is-active --quiet "$svc" || fail "service_changed"
    [[ "$(systemctl show "$svc" -p MainPID --value)" == "${BEFORE_PIDS[$svc]}" ]] ||
        fail "service_pid_changed"
done
echo "FOREST001_WEB_PUBLISHED source_commit=$SHA url=$url/"
echo "FOREST001_NOV_PREVIEW_PRESERVED"
echo "FOREST001_NO_SERVICE_RESTART"
echo "FOREST001_WEB_BACKUP_PATH=$BACKUP/site"
