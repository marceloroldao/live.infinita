#!/usr/bin/env bash
set -Eeuo pipefail

REPO="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
CACHE=/var/cache/live-infinita-godot
ENGINE=/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64
WEB=/var/www/live-infinita-godot/index.html

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/recover-disk-and-apply-spatial-008w.sh" >&2
  exit 1
fi

echo "[008w] Disco antes:"
df -h /

[[ -x "$ENGINE" ]] || { echo "[008w] Godot instalado ausente; abortando." >&2; exit 1; }
[[ -s "$WEB" ]] || { echo "[008w] export Web atual ausente; abortando." >&2; exit 1; }

echo "[008w] Limpando apenas caches/logs descartáveis..."
journalctl --rotate || true
journalctl --vacuum-size=200M || true
apt-get clean

if [[ -d "$CACHE" ]]; then
  rm -f --     "$CACHE/Godot_v4.7.2-stable_linux.x86_64.zip"     "$CACHE/Godot_v4.7.2-stable_export_templates.tpz"
fi

sync

[[ -x "$ENGINE" ]] || { echo "[008w] Godot instalado foi afetado; abortando." >&2; exit 1; }
[[ -s "$WEB" ]] || { echo "[008w] export Web foi afetado; abortando." >&2; exit 1; }

available_kb="$(df -Pk / | awk 'NR==2 {print $4}')"
if [[ ! "$available_kb" =~ ^[0-9]+$ ]] || (( available_kb < 1048576 )); then
  echo "[008w] Espaço ainda abaixo de 1 GiB; não executarei o deploy." >&2
  df -h /
  exit 1
fi

echo "[008w] Disco após limpeza:"
df -h /

echo "[008w] Aplicando 008v com filesystem recuperado..."
cd "$REPO"
bash deploy/apply-spatial-deploy-quiesce-008v.sh

echo "[008w] Validação final:"
df -h /
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-memoria-local.service
curl -fsS --max-time 10 http://127.0.0.1:8080/api/health >/dev/null
echo "[008w] OK"
