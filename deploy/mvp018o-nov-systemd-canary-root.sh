#!/usr/bin/env bash
# MVP-018O root-only, one-shot TEMPORARY sandbox trial and guaranteed cleanup.
# Invoked only after a real operator executes sudo -v in their own terminal.
set -Eeuo pipefail
umask 077
fail(){ echo "MVP018O_SYSTEMD_BLOCKED: $1" >&2; exit 2; }
[[ "$EUID" -eq 0 && $# -eq 1 && "$1" =~ ^[a-f0-9]{40}$ ]] ||
  fail "root_or_commit_invalid"
SHA="$1"
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
BASE=/opt/live-infinita-nov-preparer/releases
RELEASE="$BASE/$SHA"
UNIT=live-infinita-nov-memory-prepare-canary.service
UNIT_PATH="/run/systemd/system/$UNIT"
MAIN_UNIT=live-infinita-nov-memory-prepare.service

exec 9>/run/lock/live-infinita-nov-ephemeral-canary.lock
flock -n 9 || fail "already_running"
[[ -x "$PY" && -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] ||
  fail "pinned_runtime_missing"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" rev-parse HEAD)" == "$SHA" ]] ||
  fail "repo_version_moved"
[[ "$(git -c safe.directory="$REPO" -C "$REPO" branch --show-current)" == main ]] ||
  fail "repo_not_main"
[[ -z "$(git -c safe.directory="$REPO" -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
  fail "dirty_checkout"
[[ "$(systemctl is-enabled "$MAIN_UNIT" 2>/dev/null || true)" == not-found ]] ||
  fail "permanent_unit_already_present"
[[ ! -e "$UNIT_PATH" && ! -L "$UNIT_PATH" ]] || fail "canary_unit_present"
[[ ! -e "$RELEASE" && ! -L "$RELEASE" ]] || fail "release_already_present"
for name in live-infinita-autonomous-world.service live-infinita-memoria-local.service; do
  systemctl is-active --quiet "$name" || fail "existing_service_unavailable"
done

WORK="$(mktemp -d /tmp/live-nov-systemd.XXXXXXXX)"
created=0
installed=0
cleanup(){
  rc=$?
  trap - EXIT INT TERM
  set +e
  stopped=1
  if [[ "$installed" == 1 ]]; then
    systemctl stop "$UNIT" >/dev/null 2>&1
    if systemctl is-active --quiet "$UNIT"; then
      stopped=0
    fi
    main_pid="$(systemctl show "$UNIT" --property=MainPID --value 2>/dev/null)"
    if [[ -n "$main_pid" && "$main_pid" != 0 ]]; then
      stopped=0
    fi
    if [[ "$stopped" == 1 ]]; then
      rm -f -- "$UNIT_PATH"
      systemctl daemon-reload >/dev/null 2>&1
      systemctl reset-failed "$UNIT" >/dev/null 2>&1
    else
      echo "MVP018O_ROLLBACK_BLOCKED process_still_active" >&2
      rc=2
    fi
  fi
  if [[ "$stopped" == 1 ]]; then
    # The dedicated 0700 RuntimeDirectory contains only ephemeral V2 copies.
    # systemd normally removes it; ensure no scratch remains after a safe stop.
    if [[ -d /run/live-infinita-nov-preparer &&
          ! -L /run/live-infinita-nov-preparer ]]; then
      rm -rf -- /run/live-infinita-nov-preparer
    fi
  fi
  if [[ "$stopped" == 1 && "$created" == 1 &&
        "$RELEASE" =~ ^/opt/live-infinita-nov-preparer/releases/[a-f0-9]{40}$ ]]; then
    rm -rf -- "$RELEASE"
    rmdir "$BASE" /opt/live-infinita-nov-preparer >/dev/null 2>&1
  fi
  rm -rf -- "$WORK"
  if [[ "$installed" == 1 && ( -e "$UNIT_PATH" || -L "$UNIT_PATH" ) ]]; then
    echo "MVP018O_ROLLBACK_BLOCKED unit_file" >&2
    rc=2
  fi
  if [[ "$created" == 1 && -e "$RELEASE" ]]; then
    echo "MVP018O_ROLLBACK_BLOCKED release_file" >&2
    rc=2
  fi
  if [[ -e /run/live-infinita-nov-preparer ||
        -L /run/live-infinita-nov-preparer ]]; then
    echo "MVP018O_ROLLBACK_BLOCKED runtime_scratch" >&2
    rc=2
  fi
  if [[ "$rc" == 0 ]]; then
    echo "MVP018O_ROLLBACK_OK"
    echo "MVP018O_NO_PERMANENT_UNIT_OR_CUTOVER"
  else
    echo "MVP018O_TRIAL_BLOCKED_AND_CLEANUP_ATTEMPTED" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# Copy public source from the exact checked Git object, never a writable /home
# working-tree file, into root-owned, version-addressed private release path.
install -d -o root -g root -m 0755 /opt/live-infinita-nov-preparer "$BASE"
install -d -o root -g root -m 0755 "$RELEASE"
created=1
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache \
  nov_memory_context_shadow nov_trajectory_recall_shadow nov_memory_hybrid_shadow \
  nov_memory_dual_lane_shadow nov_memory_async_prepare nov_memory_current_frame \
  nov_memory_continuous nov_memory_release_contract nov_memory_systemd_canary; do
  git -c safe.directory="$REPO" -C "$REPO" show \
    "$SHA:apps/world-runtime/$name.py" > "$RELEASE/$name.py" ||
    fail "public_git_module_missing"
  chown root:root "$RELEASE/$name.py"
  chmod 0644 "$RELEASE/$name.py"
done
[[ "$(stat -c %u "$RELEASE")" == 0 ]] || fail "root_release_owner"
PYTHONPYCACHEPREFIX="$WORK/pycache" "$PY" -m compileall -q "$RELEASE" ||
  fail "public_code_compile"
echo "MVP018O_ROOT_RELEASE_OK"

# Render the exact production hardening settings, changing ONLY finite cycles
# and Restart=no. This canary has no [Install] section, and is in /run only.
git -c safe.directory="$REPO" -C "$REPO" show \
  "$SHA:deploy/live-infinita-nov-memory-prepare.service" > "$WORK/template.service" ||
  fail "public_git_template_missing"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$RELEASE:$CORE" "$PY" \
  "$RELEASE/nov_memory_systemd_canary.py" \
  --root "$RELEASE" --template "$WORK/template.service" \
  --unit-out "$RELEASE/$UNIT" || fail "unit_render"
systemd-analyze verify "$RELEASE/$UNIT" >"$WORK/verify.out" 2>&1 ||
  fail "systemd_verify"
install -o root -g root -m 0644 "$RELEASE/$UNIT" "$UNIT_PATH"
installed=1
systemctl daemon-reload >/dev/null || fail "systemd_reload"
[[ "$(systemctl show "$UNIT" --property=User --value)" == liveinfinita ]] ||
  fail "unit_user_mismatch"
[[ "$(systemctl show "$UNIT" --property=Group --value)" == liveinfinita ]] ||
  fail "unit_group_mismatch"
echo "MVP018O_EPHEMERAL_UNIT_READY"
SINCE="$(date --utc '+%Y-%m-%d %H:%M:%S')"
systemctl start "$UNIT" || fail "unit_start"
echo "MVP018O_EPHEMERAL_UNIT_RUNNING"
state=unknown
# 60 continuous-mode cycles at 2 s plus bounded owner cleanup.
for ((t=0;t<165;t++)); do
  state="$(systemctl show "$UNIT" --property=ActiveState --value)"
  [[ "$state" == inactive || "$state" == failed ]] && break
  sleep 1
done
[[ "$state" == inactive ]] || fail "unit_did_not_complete"
[[ "$(systemctl show "$UNIT" --property=Result --value)" == success ]] ||
  fail "unit_result_failed"
[[ "$(systemctl show "$UNIT" --property=ExecMainStatus --value)" == 0 ]] ||
  fail "unit_exit_nonzero"
journalctl --no-pager --output=cat -u "$UNIT" --since "$SINCE" > "$WORK/journal.txt" ||
  fail "journal_unavailable"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$RELEASE:$CORE" "$PY" \
  "$RELEASE/nov_memory_systemd_canary.py" \
  --root "$RELEASE" --template "$WORK/template.service" \
  --unit-out "$RELEASE/$UNIT" --journal "$WORK/journal.txt" ||
  fail "canary_aggregate_rejected"
for name in live-infinita-autonomous-world.service live-infinita-memoria-local.service; do
  systemctl is-active --quiet "$name" || fail "existing_service_changed"
done
[[ "$(systemctl is-enabled "$MAIN_UNIT" 2>/dev/null || true)" == not-found ]] ||
  fail "permanent_unit_appeared"
echo "MVP018O_SYSTEMD_FINITE_TRIAL_OK"
