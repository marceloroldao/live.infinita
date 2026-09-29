#!/usr/bin/env bash
# One-shot, OFF-by-default Nov memory recall probe. Does not touch live runtime.
set -Eeuo pipefail
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
ROOT=/var/lib/live-infinita/memoria-local
SOURCE="$ROOT/external-episodes-incremental/external-episodes.sqlite3"
CHECKPOINT="$ROOT/nov-ingest.checkpoint.json"
WORLD=/var/lib/live-infinita/autonomous-world/world.json
fail(){ echo "MVP018E_NOV_RECALL_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail "execute como etbra"
[[ -f "$REPO/apps/world-runtime/nov_memory_recall_shadow.py" ]] || fail "script ausente"
[[ -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] || fail "core V2 pin ausente"
[[ -x "$PY" ]] || fail "Python local ausente"
[[ $# -le 1 ]] || fail "opcionalmente informe apenas a necessidade"
systemctl is-active --quiet live-infinita-memoria-local.service || fail "serviço de memória inativo"
systemctl is-active --quiet live-infinita-autonomous-world.service || fail "mundo inativo"
# Read-only health verifies the current SQLite authority both before and after.
health(){
"$PY" - <<'PY'
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as reply:
    state=json.load(reply)
assert state["backend"]=="sqlite"
assert state["external_episode_persistence"]=="sqlite-incremental"
print("MVP018E_SQLITE_AUTHORITY_OK observations=",state["external_episode_observations"])
PY
}
health
args=()
if [[ $# -eq 1 && -n "$1" ]]; then
    args=(--need "$1")
fi
# The operator opens public source as stdin before sudo; liveinfinita never
# traverses /home/etbra. Private journal is not copied to the operator's home.
( cd / && sudo -u liveinfinita env PYTHONPATH="$CORE" "$PY" - \
    --private-root "$ROOT" --source "$SOURCE" --world "$WORLD" \
    --checkpoint "$CHECKPOINT" --limit 5 "${args[@]}" \
    < "$REPO/apps/world-runtime/nov_memory_recall_shadow.py" )
health
echo "MVP018E_NOV_RECALL_NO_CUTOVER"
