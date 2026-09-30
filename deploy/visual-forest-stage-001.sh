#!/usr/bin/env bash
# One operator command; sudo credentials are entered only on operator's TTY.
set -Eeuo pipefail
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
fail(){ echo "FOREST001_OPERATOR_BLOCKED: $1" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# -eq 0 ]] ||
    fail "operator_or_arguments"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || fail "not_main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "dirty_checkout"
git -C "$REPO" fetch -q origin main
git -C "$REPO" pull --ff-only origin main
SHA="$(git -C "$REPO" rev-parse HEAD)"
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || fail "commit_invalid"
[[ "$(git -C "$REPO" rev-parse origin/main)" == "$SHA" ]] || fail "not_current_main"
cd "$REPO"
"$PY" -m unittest -q tests.test_forest_stage_001 tests.test_quaternius_nature_importer ||
    fail "visual_tests_failed"
sudo -v || fail "sudo_auth_failed"
sudo -n -- bash "$REPO/deploy/visual-forest-stage-001-root.sh" "$SHA"
