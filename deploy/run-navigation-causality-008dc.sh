#!/usr/bin/env bash
set -Eeuo pipefail
REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROJECT=/home/etbra/008bz-godot-test
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
PYTHON=/opt/live.infinita/.venv/bin/python
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REPORT="/home/etbra/008dc-causality-$STAMP.json"
"$PYTHON" - "$PROJECT" "$REPO" <<'PY'
from pathlib import Path
import sys
project,repo=map(lambda p:Path(p).resolve(),sys.argv[1:])
assert project.is_relative_to(Path("/home/etbra"))
assert project!=(repo/"apps/renderer-godot").resolve()
assert (project/"project.godot").exists(),"Use the prepared isolated Godot project"
PY
rsync -a --exclude '/.godot/' --exclude '/build/' "$REPO/apps/renderer-godot/" "$PROJECT/"
"$ENGINE" --headless --audio-driver Dummy --editor --quit --path "$PROJECT" > "/home/etbra/008dc-import-$STAMP.log" 2>&1
if grep -Eiq 'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:' "/home/etbra/008dc-import-$STAMP.log"; then
    cat "/home/etbra/008dc-import-$STAMP.log"
    exit 2
fi
"$PYTHON" -u "$REPO/tools/benchmark_navigation_causality_008dc.py" --project "$PROJECT" --report "$REPORT" > "${REPORT%.json}.log" 2>&1
"$PYTHON" - "$REPORT" <<'PY'
import json,sys
r=json.load(open(sys.argv[1]))
print("Conhecimento comum:",r["eligible_shared_entries"],"ACKs:",r["api_acks"],"recuperados:",r["api_recovered"])
for row in r["comparisons"]:
    print(row["variant"],row["mode"],"distância:",round(row["distance_m"],3),
        "RAM causal:",row["causal_ram_actions"],"Memoria.ia causal:",row["causal_memoria_actions"])
print("008DC_BENCHMARK_OK report="+sys.argv[1])
PY
