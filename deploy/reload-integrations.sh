#!/usr/bin/env bash
set -euo pipefail
config=/var/lib/live-infinita/integrations.json
if [[ ! -r "$config" ]]; then
  exit 0
fi
if /opt/live.infinita/.venv/bin/python - "$config" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    value = json.load(fh)
raise SystemExit(0 if value.get("tiktok_unique_id") else 1)
PY
then
  systemctl restart live-infinita-tiktok.service
fi
