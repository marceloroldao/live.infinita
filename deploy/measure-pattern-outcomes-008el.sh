#!/usr/bin/env bash
set -euo pipefail
cd /home/etbra/live.infinita
exec python3 tools/measure_live_pattern_outcomes_008el.py \
  --output /home/etbra/008el-latest-pattern-outcomes.json \
  --capture-log /home/etbra/008el-latest-pattern-events.log "$@"
