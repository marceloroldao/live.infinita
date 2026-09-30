#!/usr/bin/env bash
# Transactional rollout for bounded persistent-region descriptors + Vale de Nov preview.
set -Eeuo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
PROD_ROOT=/opt/live.infinita
PROD_FILE="$PROD_ROOT/apps/world-runtime/spatial_session.py"
SOURCE_FILE="$SOURCE_DIR/apps/world-runtime/spatial_session.py"
CHECKER="$SOURCE_DIR/deploy/check-spatial-region-descriptors.py"
BACKUP="$(mktemp /tmp/live-infinita-spatial-session.XXXXXX.py)"
CHANGED=0

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/world-map-regions-003-root.sh" >&2
  exit 1
fi

cleanup() {
  rm -f -- "$BACKUP"
}
rollback() {
  local rc=$?
  if (( CHANGED == 1 )); then
    echo "[regions-003] Falha; restaurando SpatialSession anterior." >&2
    cp -- "$BACKUP" "$PROD_FILE"
    chown liveinfinita:liveinfinita "$PROD_FILE"
    chmod 0664 "$PROD_FILE"
    systemctl restart live-infinita || true
  fi
  cleanup
  exit "$rc"
}
trap rollback ERR
trap cleanup EXIT

[[ -f "$SOURCE_FILE" && -f "$PROD_FILE" && -f "$CHECKER" ]] || {
  echo "[regions-003] Arquivo obrigatório ausente." >&2
  exit 2
}

echo "[regions-003] Validando testes antes de tocar produção."
cd "$SOURCE_DIR"
python3 -m unittest   tests.test_spatial_session   tests.test_spatial_session_cold_store   tests.test_world_map_001

cp -- "$PROD_FILE" "$BACKUP"
install -o liveinfinita -g liveinfinita -m 0664 "$SOURCE_FILE" "$PROD_FILE"
CHANGED=1

echo "[regions-003] Reiniciando somente o runtime autoritativo."
systemctl restart live-infinita

echo "[regions-003] Aguardando health."
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/api/health >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null

echo "[regions-003] Validando fatia espacial WebSocket."
"$PROD_ROOT/.venv/bin/python" "$CHECKER"

echo "[regions-003] Publicando preview Web isolado."
bash "$SOURCE_DIR/deploy/export-world-map-preview-web.sh"

echo "[regions-003] Verificando endpoints."
curl -fsS --max-time 10 https://live.etbra.com.br/godot/world-map-preview/build.json
printf '\n'
curl -fsS --max-time 10 https://live.etbra.com.br/godot/ >/dev/null
curl -fsS --max-time 10 https://live.etbra.com.br/godot/nov-preview/ >/dev/null

CHANGED=0
trap - ERR
cleanup
echo "[regions-003] OK: runtime + preview atualizados; live principal preservada."
