#!/usr/bin/env bash
set -euo pipefail
cd /home/etbra/live.infinita
exec python3 tools/run_contact_turns_008et.py \
  --output-dir /home/etbra/008et-contact-turn-proof "$@"
