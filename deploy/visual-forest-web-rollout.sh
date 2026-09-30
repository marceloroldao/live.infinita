#!/usr/bin/env bash
# Visual 001 Web-only rollout. One command from the operator's mobile TTY.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
LOG="$HOME/forest-web-rollout.log"
fail(){ echo "FOREST_WEB_OPERATOR_BLOCKED $1" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# == 0 ]] || fail "operator_or_arguments"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || fail "not_main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] || fail "dirty_checkout"
git -C "$REPO" fetch -q origin main
git -C "$REPO" pull --ff-only origin main
SHA="$(git -C "$REPO" rev-parse HEAD)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ && "$(git -C "$REPO" rev-parse origin/main)" == "$SHA" ]] || fail "checkout_not_current"
[[ ! -L "$LOG" ]] || fail "log_symlink"
cd "$REPO"
"/opt/live.infinita/.venv/bin/python" -m unittest -q tests.test_forest_stage_001 tests.test_forest_web_rollout_001 || fail "visual_contract_tests"
sudo -v || fail "sudo_auth"
: > "$LOG"
chmod 0600 "$LOG"
sudo -n -- bash "$REPO/deploy/visual-forest-web-rollout-root.sh" "$SHA" 2>&1 | tee "$LOG"
echo "FOREST_WEB_OPERATOR_LOG_READY $LOG"
