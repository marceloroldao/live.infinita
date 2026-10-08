#!/usr/bin/env bash
set -euo pipefail
repo=/home/etbra/live.infinita
project=/home/etbra/008ep-godot-test
mkdir -p "$project"
rsync -a --exclude '/.godot/' --exclude '/build/' "$repo/apps/renderer-godot/" "$project/"
/opt/live.infinita/.venv/bin/python "$repo/tools/run_cost_shift_matrix_008ep.py" --project "$project" --output-dir /home/etbra/008ep-results
