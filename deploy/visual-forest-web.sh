#!/usr/bin/env bash
# Visual 001 Web: one operator command; git and sudo auth stay in operator TTY.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
fail(){ echo "FOREST001_WEB_OPERATOR_BLOCKED: $1" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# -eq 0 ]] ||
    fail "operator_or_arguments"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] ||
    fail "not_main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "dirty_checkout"
git -C "$REPO" fetch -q origin main
git -C "$REPO" pull --ff-only origin main
SHA="$(git -C "$REPO" rev-parse HEAD)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "commit_invalid"
[[ "$(git -C "$REPO" rev-parse origin/main)" == "$SHA" ]] ||
    fail "checkout_not_current"
cd "$REPO"
"$PY" -m unittest -q tests.test_forest_stage_001 \
    tests.test_forest_rollout_001 tests.test_forest_web_rollout_001 ||
    fail "visual_gates_failed"
sudo -v || fail "sudo_auth_failed"
sudo -n -- bash "$REPO/deploy/visual-forest-web-root.sh" "$SHA"
