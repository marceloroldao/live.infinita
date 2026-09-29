#!/usr/bin/env bash
# MVP-018N: PUBLIC-CODE-ONLY immutable release layout and unit render preflight.
# Never installs, starts, stops, enables or restarts a systemd service.
set -Eeuo pipefail
umask 077
REPO=/home/etbra/live.infinita
PY=/opt/live.infinita/.venv/bin/python
CORE=/opt/live-infinita-memoria-core/2b6334e8d6026c6bae620297de3f2fa658427596/src
fail(){ echo "MVP018N_PREFLIGHT_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 && $# -eq 0 ]] || fail "usuario ou argumentos invalidos"
[[ -x "$PY" && -f "$CORE/memoria_resolutiva/external_episode_incremental.py" ]] ||
    fail "runtime ou core V2 pin indisponivel"
[[ "$(git -C "$REPO" branch --show-current)" == main ]] || fail "checkout fora da main"
[[ -z "$(git -C "$REPO" status --porcelain --untracked-files=no)" ]] ||
    fail "checkout com alteracoes rastreadas"
[[ "$(systemctl is-enabled live-infinita-nov-memory-prepare.service 2>/dev/null || true)" == not-found ]] ||
    fail "unidade ja instalada ou habilitada"
for unit in live-infinita-autonomous-world.service live-infinita-memoria-local.service; do
    systemctl is-active --quiet "$unit" || fail "servico atual inativo"
done
STAGE="$(mktemp -d /tmp/live-nov-preflight.XXXXXXXX)"
cleanup(){ rm -rf -- "$STAGE"; }
trap cleanup EXIT
chmod 0755 "$STAGE"
for name in memoria_v2_adapter nov_memory_recall_shadow nov_memory_recall_cache \
    nov_memory_context_shadow nov_trajectory_recall_shadow nov_memory_hybrid_shadow \
    nov_memory_dual_lane_shadow nov_memory_async_prepare nov_memory_current_frame \
    nov_memory_continuous nov_memory_release_contract; do
    original="$REPO/apps/world-runtime/$name.py"
    [[ -f "$original" && ! -L "$original" ]] || fail "modulo publico indisponivel"
    cp -- "$original" "$STAGE/$name.py"
    chmod 0644 "$STAGE/$name.py"
    cmp -s -- "$original" "$STAGE/$name.py" || fail "copia divergente"
done
echo "MVP018N_BUNDLE_OK"
PYTHONDONTWRITEBYTECODE=1 "$PY" "$STAGE/nov_memory_release_contract.py" \
    --root "$STAGE" \
    --template "$REPO/deploy/live-infinita-nov-memory-prepare.service" \
    --output "$STAGE/live-infinita-nov-memory-prepare.service"
PYTHONPYCACHEPREFIX="$STAGE/pycache" "$PY" -m compileall -q "$STAGE" ||
    fail "compilacao falhou"
systemd-analyze verify "$STAGE/live-infinita-nov-memory-prepare.service" ||
    fail "unit template nao passou systemd-analyze verify"
echo "MVP018N_SYSTEMD_TEMPLATE_OK"
[[ "$(systemctl is-enabled live-infinita-nov-memory-prepare.service 2>/dev/null || true)" == not-found ]] ||
    fail "unidade mudou durante preflight"
echo "MVP018N_NOT_INSTALLED_OR_STARTED"
