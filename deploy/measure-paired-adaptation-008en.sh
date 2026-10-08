#!/usr/bin/env bash
set -euo pipefail
repo=/home/etbra/live.infinita
project=/home/etbra/008en-godot-test
output=/home/etbra/008en-paired-results
mkdir -p "$project"
rsync -a --exclude '/.godot/' --exclude '/build/' "$repo/apps/renderer-godot/" "$project/"
/opt/live.infinita/.venv/bin/python "$repo/tools/run_paired_adaptation_008en.py" --project "$project" --output-dir "$output"
