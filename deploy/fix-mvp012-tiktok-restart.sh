#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/fix-mvp012-tiktok-restart.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
bridge=/opt/live.infinita/apps/sources/tiktok_live_bridge.py
unit=/etc/systemd/system/live-infinita-tiktok.service
printf '%s  %s\n' 473560680ddf08635821f2b0743dc5230bdd5c3bfb14f0dd4d5df6820482ef41 "$bridge" | sha256sum --check --status
printf '%s  %s\n' 97dba2c1a9d43e1ed09d1cf87572844eab5e435de6bfd8687a8aa47b15bc7856 "$unit" | sha256sum --check --status

backup=$(mktemp -d /var/backups/live-infinita-tiktok-restart.XXXXXX)
chmod 700 "$backup"
cp -p "$bridge" "$backup/tiktok_live_bridge.py"
cp -p "$unit" "$backup/live-infinita-tiktok.service"
echo "Backup: $backup"

changed=0
recover() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $changed -eq 1 ]]; then
    systemctl stop live-infinita-tiktok || true
    cp -p "$backup/tiktok_live_bridge.py" "$bridge"
    cp -p "$backup/live-infinita-tiktok.service" "$unit"
    systemctl daemon-reload || true
    echo "Reparo não aplicado; arquivos restaurados de $backup" >&2
  fi
  exit "$result"
}
trap recover EXIT

changed=1
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/sources/tiktok_live_bridge.py" "$bridge"
install -o root -g root -m 0644 "$source_dir/deploy/live-infinita-tiktok.service" "$unit"
systemctl daemon-reload
systemctl enable live-infinita-tiktok
systemctl restart live-infinita-tiktok
for attempt in {1..30}; do
  [[ -s /var/lib/live-infinita/tiktok-status.json ]] && break
  sleep 1
done
systemctl is-active --quiet live-infinita-tiktok
test -s /var/lib/live-infinita/tiktok-status.json
echo 'Conector TikTok ativo com reinício limpo e monitoramento habilitado.'
