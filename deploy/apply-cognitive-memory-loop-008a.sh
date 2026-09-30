#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
[[ ${EUID} -eq 0 ]] || {
  echo "Execute: sudo bash deploy/apply-cognitive-memory-loop-008a.sh" >&2
  exit 1
}

BACKUP="$(mktemp -d /tmp/live-cognitive-008a.XXXXXX)"
declare -a DESTS=(
  /opt/live.infinita/apps/world-runtime/main_live.py
  /opt/live.infinita/apps/world-runtime/main_cognitive_live.py
  /opt/live.infinita/apps/world-runtime/cognitive_evidence_sync.py
  /opt/live.infinita/packages/observability/cognitive_evidence.py
  /etc/systemd/system/live-infinita-cognitive-evidence-sync.service
  /etc/systemd/system/live-infinita-cognitive-evidence-sync.timer
)

for i in "${!DESTS[@]}"; do
  if [[ -e "${DESTS[$i]}" ]]; then
    cp -a -- "${DESTS[$i]}" "$BACKUP/$i"
  else
    : >"$BACKUP/$i.absent"
  fi
done

rollback() {
  local rc=$?
  set +e
  systemctl disable --now live-infinita-cognitive-evidence-sync.timer >/dev/null 2>&1
  for i in "${!DESTS[@]}"; do
    if [[ -f "$BACKUP/$i.absent" ]]; then
      rm -f -- "${DESTS[$i]}"
    else
      cp -a -- "$BACKUP/$i" "${DESTS[$i]}"
    fi
  done
  systemctl daemon-reload
  systemctl restart live-infinita.service
  rm -rf -- "$BACKUP"
  echo "[008a] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

echo "[008a] Instalando código cognitivo e unidades..."
install -o liveinfinita -g liveinfinita -m 0664 apps/world-runtime/main_live.py /opt/live.infinita/apps/world-runtime/main_live.py
install -o liveinfinita -g liveinfinita -m 0664 apps/world-runtime/main_cognitive_live.py /opt/live.infinita/apps/world-runtime/main_cognitive_live.py
install -o liveinfinita -g liveinfinita -m 0664 apps/world-runtime/cognitive_evidence_sync.py /opt/live.infinita/apps/world-runtime/cognitive_evidence_sync.py
install -o liveinfinita -g liveinfinita -m 0664 packages/observability/cognitive_evidence.py /opt/live.infinita/packages/observability/cognitive_evidence.py

install -o root -g root -m 0644 deploy/live-infinita-cognitive-evidence-sync.service /etc/systemd/system/live-infinita-cognitive-evidence-sync.service
install -o root -g root -m 0644 deploy/live-infinita-cognitive-evidence-sync.timer /etc/systemd/system/live-infinita-cognitive-evidence-sync.timer

systemctl daemon-reload
systemctl restart live-infinita.service
systemctl enable --now live-infinita-cognitive-evidence-sync.timer

echo "[008a] Verificando runtime..."
for _ in $(seq 1 30); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/api/health >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS --max-time 5 http://127.0.0.1:8080/api/health >/dev/null
systemctl is-active --quiet live-infinita.service
systemctl is-active --quiet live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-cognitive-evidence-sync.timer

if [[ -s /var/lib/live-infinita/cognitive-evidence.jsonl ]]; then
  echo "[008a] Sincronizando evidência pendente..."
  systemctl start live-infinita-cognitive-evidence-sync.service
fi

trap - ERR
rm -rf -- "$BACKUP"
echo "[008a] OK: audiência + narrador ligados à Memoria.ia local em trilhas separadas."
