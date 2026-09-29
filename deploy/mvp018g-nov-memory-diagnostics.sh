#!/usr/bin/env bash
# MVP-018G: single-command read-only owner-side cache and diversity diagnostic.
# Public code only is staged in /tmp; private memory never leaves its 0700 root.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
ROOT=/var/lib/live-infinita/memoria-local
SOURCE="$ROOT/external-episodes-incremental/external-episodes.sqlite3"
CHECKPOINT="$ROOT/nov-ingest.checkpoint.json"
WORLD=/var/lib/live-infinita/autonomous-world/world.json
LOG="$HOME/nov-memory-diagnostics.log"
fail(){ echo "MVP018G_NOV_DIAGNOSTICS_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail "execute como etbra"
[[ $# -eq 0 ]] || fail "sem argumentos"
[[ -x "$PY" ]] || fail "Python local indisponivel"
[[ -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] || fail "core V2 pin indisponivel"
[[ ! -L "$LOG" ]] || fail "log nao pode ser symlink"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache nov_memory_context_shadow nov_memory_diagnostics; do
    [[ -f "$REPO/apps/world-runtime/$name.py" ]] || fail "modulo ausente: $name"
done
systemctl is-active --quiet live-infinita-memoria-local.service || fail "Memoria.ia local inativa"
systemctl is-active --quiet live-infinita-autonomous-world.service || fail "mundo inativo"
STAGE="$(mktemp -d /tmp/live-nov-diagnostics.XXXXXXXX)"
cleanup(){ rm -rf -- "$STAGE"; }
trap cleanup EXIT
chmod 0755 "$STAGE"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache nov_memory_context_shadow nov_memory_diagnostics; do
    cp -- "$REPO/apps/world-runtime/$name.py" "$STAGE/$name.py"
    chmod 0644 "$STAGE/$name.py"
done
: > "$LOG"
chmod 0600 "$LOG"
health(){
"$PY" - <<'PY'
import json
from urllib.request import urlopen
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as response:
    value=json.load(response)
assert value["backend"]=="sqlite" and value["external_episode_persistence"]=="sqlite-incremental"
print("MVP018G_SQLITE_AUTHORITY_OK observations=", value["external_episode_observations"])
PY
}
run(){
    health
    (cd / && sudo -u liveinfinita env PYTHONPATH="$STAGE:$CORE" "$PY" "$STAGE/nov_memory_diagnostics.py" \
        --private-root "$ROOT" --source "$SOURCE" --checkpoint "$CHECKPOINT" \
        --world "$WORLD" --samples 20)
    health
    echo "MVP018G_NO_CUTOVER_OR_WORLD_CHANGE"
}
run 2>&1 | tee "$LOG"
echo "MVP018G_PRIVATE_REDACTED_LOG_READY"
