#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute com sudo: sudo bash deploy/apply-nov-exploration-007.sh" >&2
  exit 1
fi

echo "[007] Backup dos arquivos atuais..."
cp -a /opt/live.infinita/apps/world-runtime/npc_idle_wander.py   /opt/live.infinita/apps/world-runtime/npc_idle_wander.py.pre-007
cp -a /opt/live.infinita/packages/spatial/agent_intent.py   /opt/live.infinita/packages/spatial/agent_intent.py.pre-007

echo "[007] Instalando nova exploração..."
install -o liveinfinita -g liveinfinita -m 0664   apps/world-runtime/npc_idle_wander.py   /opt/live.infinita/apps/world-runtime/npc_idle_wander.py

install -o liveinfinita -g liveinfinita -m 0664   packages/spatial/agent_intent.py   /opt/live.infinita/packages/spatial/agent_intent.py

echo "[007] Reiniciando serviços..."
systemctl restart live-infinita-autonomous-world.service live-infinita.service

echo "[007] Verificando serviços..."
systemctl is-active --quiet live-infinita-autonomous-world.service
systemctl is-active --quiet live-infinita.service

echo "[007] OK: exploração 007 instalada."
