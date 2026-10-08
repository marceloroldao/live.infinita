#!/usr/bin/env bash
set -euo pipefail
repo=/home/etbra/live.infinita
project=/home/etbra/008eq-godot-test
mkdir -p "$project"
rsync -a --exclude '/.godot/' --exclude '/build/' "$repo/apps/renderer-godot/" "$project/"
/opt/live.infinita/.venv/bin/python "$repo/tools/run_repeated_changes_008eq.py" --project "$project" --output-dir /home/etbra/008eq-results
