#!/usr/bin/env bash
# MVP-018L — bounded live-frame read-only Nov owner pilot.
# Never starts, stops, restarts or enables a service.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
ROOT=/var/lib/live-infinita/memoria-local
SOURCE="$ROOT/external-episodes-incremental/external-episodes.sqlite3"
CHECKPOINT="$ROOT/nov-ingest.checkpoint.json"
WORLD=/var/lib/live-infinita/autonomous-world/world.json
COLD=/var/lib/live-infinita/autonomous-world/cold-store
LOG="$HOME/nov-live-frame-pilot.log"
fail(){ echo "MVP018L_PILOT_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail "execute como etbra"
[[ $# -eq 0 ]] || fail "sem argumentos"
[[ -x "$PY" ]] || fail "Python local indisponivel"
[[ -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] || fail "core V2 pin indisponivel"
[[ -d "$COLD/regions" ]] || fail "cold store indisponivel"
[[ ! -L "$LOG" ]] || fail "log nao pode ser symlink"
systemctl is-active --quiet live-infinita-autonomous-world.service || fail "mundo inativo"
systemctl is-active --quiet live-infinita-memoria-local.service || fail "Memoria.ia local inativa"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache nov_memory_context_shadow nov_trajectory_recall_shadow nov_memory_hybrid_shadow nov_memory_dual_lane_shadow nov_memory_async_prepare nov_memory_live_frame_pilot; do
    [[ -f "$REPO/apps/world-runtime/$name.py" ]] || fail "modulo publico indisponivel: $name"
done
STAGE="$(mktemp -d /tmp/live-nov-pilot.XXXXXXXX)"
cleanup(){ rm -rf -- "$STAGE"; }
trap cleanup EXIT
chmod 0755 "$STAGE"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache nov_memory_context_shadow nov_trajectory_recall_shadow nov_memory_hybrid_shadow nov_memory_dual_lane_shadow nov_memory_async_prepare nov_memory_live_frame_pilot; do
    cp -- "$REPO/apps/world-runtime/$name.py" "$STAGE/$name.py"
    chmod 0644 "$STAGE/$name.py"
done
: > "$LOG"
chmod 0600 "$LOG"
run(){
    echo "MVP018L_OWNER_ONLY_NO_SERVICE_CHANGE"
    (cd / && sudo -u liveinfinita env PYTHONPATH="$STAGE:$CORE" "$PY" "$STAGE/nov_memory_live_frame_pilot.py" \
        --private-root "$ROOT" --source "$SOURCE" --checkpoint "$CHECKPOINT" \
        --world "$WORLD" --cold-store "$COLD" --cycles 20 --interval 1)
    echo "MVP018L_NO_CUTOVER_OR_WORLD_CHANGE"
}
run 2>&1 | tee "$LOG"
echo "MVP018L_PRIVATE_REDACTED_LOG_READY"
