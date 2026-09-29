#!/usr/bin/env bash
# MVP-018M: two-minute finite owner-only operational canary.
# No service install/enable/restart, IPC, world writing or authority changes.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
LOG="$HOME/nov-memory-extended-canary.log"
fail(){ echo "MVP018M_GATE_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail "execute como etbra"
[[ $# -eq 0 ]] || fail "sem argumentos"
[[ -x "$PY" && -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] ||
  fail "runtime ou core V2 pin indisponivel"
[[ ! -L "$LOG" ]] || fail "log nao pode ser symlink"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || fail "checkout fora da main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
  fail "checkout com alteracoes rastreadas"
systemctl is-active --quiet live-infinita-autonomous-world.service || fail "mundo inativo"
systemctl is-active --quiet live-infinita-memoria-local.service || fail "Memoria.ia inativa"

STAGE="$(mktemp -d /tmp/live-nov-extended.XXXXXXXX)"
cleanup(){ rm -rf -- "$STAGE"; }
trap cleanup EXIT
chmod 0755 "$STAGE"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache \
  nov_memory_context_shadow nov_trajectory_recall_shadow nov_memory_hybrid_shadow \
  nov_memory_dual_lane_shadow nov_memory_async_prepare nov_memory_current_frame \
  nov_memory_continuous nov_memory_operational_gate; do
    [[ -f "$REPO/apps/world-runtime/$name.py" ]] || fail "modulo ausente: $name"
    cp -- "$REPO/apps/world-runtime/$name.py" "$STAGE/$name.py"
    chmod 0644 "$STAGE/$name.py"
done
# Authenticate in the actual operator TTY, before capturing the redacted run.
sudo -v || fail "sudo nao autenticado"
: > "$LOG"
chmod 0600 "$LOG"
echo "MVP018M_OWNER_ONLY_NO_SERVICE_CHANGE"
(cd / && sudo -n -u liveinfinita env PYTHONPATH="$STAGE:$CORE" "$PY" \
    "$STAGE/nov_memory_continuous.py" --canary --cycles 60 --period 2 --refresh 4) \
    2>&1 | tee "$LOG"
PYTHONPATH="$STAGE:$CORE" "$PY" "$STAGE/nov_memory_operational_gate.py" \
    --log "$LOG" | tee -a "$LOG"
systemctl is-active --quiet live-infinita-autonomous-world.service ||
  fail "mundo ficou inativo"
systemctl is-active --quiet live-infinita-memoria-local.service ||
  fail "Memoria.ia ficou inativa"
echo "MVP018M_NO_SERVICE_INSTALL_OR_CUTOVER" | tee -a "$LOG"
echo "MVP018M_PRIVATE_REDACTED_LOG_READY"
