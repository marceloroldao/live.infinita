#!/usr/bin/env bash
# One explicit operator command; sudo authentication stays in operator TTY.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
LOG="$HOME/nov-memory-systemd-canary.log"
fail(){ echo "MVP018O_OPERATOR_BLOCKED: $1" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# -eq 0 ]] ||
  fail "user_or_arguments"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] ||
  fail "not_main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
  fail "tracked_changes"
[[ ! -L "$LOG" ]] || fail "log_symlink"
SHA="$(git -C "$REPO" rev-parse HEAD)"
[[ "$SHA" =~ ^[a-f0-9]{40}$ ]] || fail "commit_invalid"
[[ -f "$REPO/deploy/mvp018o-nov-systemd-canary-root.sh" ]] ||
  fail "script_unavailable"
sudo -v || fail "sudo_authentication"
: > "$LOG"
chmod 0600 "$LOG"
sudo -n -- bash "$REPO/deploy/mvp018o-nov-systemd-canary-root.sh" "$SHA" 2>&1 |
  tee "$LOG"
echo "MVP018O_OPERATOR_REDACTED_LOG_READY"
