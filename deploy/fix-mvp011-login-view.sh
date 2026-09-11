#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/fix-mvp011-login-view.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manager=/opt/live.infinita/apps/manager
printf '%s  %s\n' bbe71b120a329cfe7cc586ce32f4f10cf773dae911069e738ab69b789c7d668c "$manager/index.html" | sha256sum --check --status
backup=$(mktemp -d /var/backups/live-infinita-login-view.XXXXXX)
chmod 700 "$backup"
cp -p "$manager/index.html" "$backup/index.html"
echo "Backup: $backup"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/index.html" "$manager/index.html"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/visibility.css" "$manager/visibility.css"
grep -q 'visibility.css' "$manager/index.html"
grep -q 'display: none !important' "$manager/visibility.css"
echo 'Correção visual aplicada. Atualize a página no navegador.'
