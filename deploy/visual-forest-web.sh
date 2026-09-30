#!/usr/bin/env bash
# Web-only forest rollout. Git and sudo authentication remain in etbra's TTY.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
fail(){ echo "FOREST_WEB_OPERATOR_BLOCKED: $1" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# -eq 0 ]] ||
    fail "operator_or_arguments"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || fail "not_main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "dirty_checkout"
git -C "$REPO" fetch -q origin main
git -C "$REPO" pull --ff-only origin main
SHA="$(git -C "$REPO" rev-parse HEAD)"
[[ "$SHA" =~ ^[a-f0-9]{40}$ &&
   "$(git -C "$REPO" rev-parse origin/main)" == "$SHA" ]] ||
    fail "commit_mismatch"
cd "$REPO"
"$PY" -m unittest -q tests.test_forest_stage_001 tests.test_forest_web_rollout ||
    fail "web_contract_tests"
sudo -v || fail "sudo_authentication"
sudo -n -- bash "$REPO/deploy/visual-forest-web-root.sh" "$SHA"
