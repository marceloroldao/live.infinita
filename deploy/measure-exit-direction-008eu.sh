#!/usr/bin/env bash
set -euo pipefail
cd /home/etbra/live.infinita
exec python3 tools/run_contact_turns_008et.py --comparison exit-direction --output-dir /home/etbra/008eu-exit-direction-proof "$@"
