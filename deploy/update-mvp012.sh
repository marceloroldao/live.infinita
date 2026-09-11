#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/update-mvp012.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/live.infinita
runtime=$install_dir/apps/world-runtime/main.py
bridge=$install_dir/apps/sources/tiktok_live_bridge.py
manager=$install_dir/apps/manager

check_hash() { printf '%s  %s\n' "$1" "$2" | sha256sum --check --status; }
check_hash 8adc1109b2c6879cb6b3581bfccc612cfc5de2f73a418174612ad72e1cf17565 "$runtime"
check_hash cf6c3f4662cee37f0dff0b6bdd38b42ecb4db2c0a31265d9ca61fdc2cdc68c45 "$bridge"
check_hash d246b0cb97061a94f2be9df7fd943069e04a8de47a2f7b8c2f976a205321d142 "$manager/index.html"
check_hash 86f55a26ccb44d5a7605760a5e0f56264d6c507e220ae11b0d1db0e9bb56edea "$manager/app.js"
check_hash 53f5e732de0ec84024dcebf4c688a56c4ada8906bbf528c076982aedfe2b2454 "$manager/style.css"
check_hash 8dca5a333a03b3cb4ca2ab16a450ac2bbc8cd35393d45002c8059ddc385d988a "$manager/visibility.css"
systemctl is-active --quiet live-infinita

backup=$(mktemp -d /var/backups/live-infinita-mvp012.XXXXXX)
chmod 700 "$backup"
echo "Backup: $backup"
cp -p "$runtime" "$backup/main.py"
cp -p "$bridge" "$backup/tiktok_live_bridge.py"
cp -p "$manager/index.html" "$backup/index.html"
cp -p "$manager/app.js" "$backup/app.js"
cp -p "$manager/style.css" "$backup/style.css"
cp -p "$manager/visibility.css" "$backup/visibility.css"
tar -C /var/lib -czf "$backup/data-before-update.tar.gz" live-infinita

changed=0
tiktok_was_active=0
systemctl is-active --quiet live-infinita-tiktok && tiktok_was_active=1 || true
recover() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $changed -eq 1 ]]; then
    echo 'Verificação falhou; restaurando MVP-011.' >&2
    systemctl stop live-infinita live-infinita-tiktok || true
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/main.py" "$runtime"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/tiktok_live_bridge.py" "$bridge"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/index.html" "$manager/index.html"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/app.js" "$manager/app.js"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/style.css" "$manager/style.css"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/visibility.css" "$manager/visibility.css"
    rm -f "$manager/monitoring.css"
    systemctl start live-infinita || true
    [[ $tiktok_was_active -eq 0 ]] || systemctl start live-infinita-tiktok || true
    echo "Dados e segredos preservados; backup em $backup" >&2
  fi
  exit "$result"
}
trap recover EXIT

systemctl stop live-infinita
[[ $tiktok_was_active -eq 0 ]] || systemctl stop live-infinita-tiktok
changed=1
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/world-runtime/main.py" "$runtime"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/sources/tiktok_live_bridge.py" "$bridge"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/index.html" "$manager/index.html"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/app.js" "$manager/app.js"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/monitoring.css" "$manager/monitoring.css"
systemctl start live-infinita
[[ $tiktok_was_active -eq 0 ]] || systemctl start live-infinita-tiktok

"$install_dir/.venv/bin/python" - <<'PY'
import json, time, urllib.error, urllib.request
base='http://127.0.0.1:8080'
def request(path, headers=None):
    with urllib.request.urlopen(urllib.request.Request(base+path, headers=headers or {}), timeout=10) as r:
        return r.status, r.read()
for attempt in range(30):
    try:
        health=json.loads(request('/api/health')[1]); break
    except OSError:
        if attempt == 29: raise
        time.sleep(1)
assert (health['mvp'],health['version']) == ('012','0.13.0'), health
assert health['replay_ok'], health
page=request('/')[1]
assert b'id="overview"' in page and b'monitoring.css' in page
token=''
with open('/etc/live-infinita/operator.env', encoding='utf-8') as fh:
    for line in fh:
        if line.startswith('LIVE_INFINITA_OPERATOR_TOKEN='):
            token=line.split('=',1)[1].strip().strip('"').strip("'")
assert token
monitor=json.loads(request('/api/manage/monitor', {'Authorization': 'Bearer '+token})[1])
assert monitor['runtime']['state']=='online' and monitor['world']['replay_ok'], monitor
serialized=json.dumps(monitor)
assert 'openai_api_key' not in serialized and 'tiktok_sign_api_key' not in serialized
print('MVP-012 validado: monitor protegido, atividade, serviços e replay OK.')
PY
systemctl is-active --quiet live-infinita
echo 'MVP-012 online. HTTPS, Godot, dados e segredos preservados.'
