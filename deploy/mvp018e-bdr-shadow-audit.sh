#!/usr/bin/env bash
# MVP-018E: validate newest private BDR shadow proof without exposing memory.
# Operator-only; no recompilation, source/BDR writes or runtime changes.
set -Eeuo pipefail
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
ROOT=/var/lib/live-infinita/memoria-local/bdr-mirrors
fail(){ echo "MVP018E_BDR_AUDIT_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail "execute como etbra"
[[ -f "$REPO/deploy/mvp018e_bdr_shadow_audit.py" ]] || fail "auditor ausente"
[[ -x "$PY" ]] || fail "Python da Memoria.ia ausente"
systemctl is-active --quiet live-infinita-memoria-local.service || fail "memória local inativa"
"$PY" - <<'PY'
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as response:
    health = json.load(response)
assert health["backend"] == "sqlite" and health["external_episode_persistence"] == "sqlite-incremental", health
print("MVP018E_AUTHORITATIVE_SQLITE_OK observations=", health["external_episode_observations"])
PY
# The private data and report are never copied to etbra or /tmp.
# The owner-only auditor prints only counts and booleans.
# The etbra shell opens the public auditor before sudo changes identity.
# Run with / as cwd: liveinfinita cannot traverse /home/etbra.
# No copy, chmod, ACL or exposure of private memory is required.
( cd / && sudo -u liveinfinita "$PY" - --mirrors-root "$ROOT" < "$REPO/deploy/mvp018e_bdr_shadow_audit.py" )
"$PY" - <<'PY'
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as response:
    health = json.load(response)
assert health["backend"] == "sqlite" and health["external_episode_persistence"] == "sqlite-incremental", health
print("MVP018E_NO_CUTOVER_OK")
PY
