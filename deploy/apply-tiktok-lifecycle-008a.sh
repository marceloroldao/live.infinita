#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ ${EUID} -ne 0 ]]; then
  echo "Execute: sudo bash deploy/apply-tiktok-lifecycle-008a.sh" >&2
  exit 1
fi

UNIT=/etc/systemd/system/live-infinita-tiktok.service
SOURCE="$ROOT/deploy/live-infinita-tiktok.service"
BACKUP="$(mktemp /tmp/live-infinita-tiktok.008a.XXXXXX.service)"
HAD_UNIT=0

if [[ -f "$UNIT" ]]; then
  cp -a -- "$UNIT" "$BACKUP"
  HAD_UNIT=1
fi

rollback() {
  local rc=$?
  set +e
  if (( HAD_UNIT == 1 )); then
    cp -a -- "$BACKUP" "$UNIT"
  else
    rm -f -- "$UNIT"
  fi
  systemctl daemon-reload
  systemctl try-restart live-infinita-tiktok.service >/dev/null 2>&1 || true
  rm -f -- "$BACKUP"
  echo "[tiktok-008a] rollback concluído." >&2
  exit "$rc"
}
trap rollback ERR

echo "[tiktok-008a] Instalando contrato de ciclo de vida..."
install -o root -g root -m 0644 "$SOURCE" "$UNIT"
systemctl daemon-reload

PART_OF="$(systemctl show live-infinita-tiktok.service -p PartOf --value)"
[[ " $PART_OF " == *" live-infinita.service "* ]] || {
  echo "PartOf não carregado: $PART_OF" >&2
  exit 2
}

systemctl enable live-infinita-tiktok.service >/dev/null
systemctl reset-failed live-infinita-tiktok.service || true
systemctl restart live-infinita-tiktok.service

sleep 1
systemctl is-enabled --quiet live-infinita-tiktok.service
systemctl is-active --quiet live-infinita.service

echo "[tiktok-008a] Estado inicial:"
systemctl show live-infinita-tiktok.service   -p ActiveState -p SubState -p MainPID -p NRestarts -p PartOf --no-pager

trap - ERR
rm -f -- "$BACKUP"
echo "[tiktok-008a] OK: restart do runtime passa a propagar para a ponte TikTok."
