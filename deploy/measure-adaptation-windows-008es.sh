#!/usr/bin/env bash
# Read-only, one capture; does not create timers or restart services.
set -euo pipefail
cd /home/etbra/live.infinita
python3 tools/measure_live_pattern_outcomes_008el.py \
  --output /home/etbra/008es-latest-pattern-outcomes.json \
  --capture-log /home/etbra/008es-latest-pattern-events.log "$@"
exec python3 tools/analyze_adaptation_windows_008es.py \
  --input /home/etbra/008es-latest-pattern-outcomes.json \
  --output /home/etbra/008es-latest-adaptation-windows.json
