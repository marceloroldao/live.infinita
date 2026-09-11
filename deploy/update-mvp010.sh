#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/update-mvp010.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/live.infinita
runtime=$install_dir/apps/world-runtime/main.py
bridge=$install_dir/apps/sources/tiktok_live_bridge.py
python=$install_dir/.venv/bin/python
path_unit=/etc/systemd/system/live-infinita-integrations.path
reload_unit=/etc/systemd/system/live-infinita-integrations-reload.service

check_hash() { printf '%s  %s\n' "$1" "$2" | sha256sum --check --status; }
check_hash fac30074d2d5293ffa956781c539b12026cdd8a89c019b5ec0562c9dfc068b57 "$runtime"
check_hash f237d28f3de452f4571bc8cab865a65d5168dbc04fbbad123c32633a24d1ba97 "$bridge"
for path in "$install_dir/apps/integrations" "$install_dir/apps/manager" "$path_unit" "$reload_unit"; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Destino inesperado já existe: $path"; exit 1; }
done
systemctl is-active --quiet live-infinita
"$python" - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/api/replay/verify', timeout=15) as r:
    assert json.load(r)['ok'], 'Replay inconsistente antes da atualização'
PY

backup=$(mktemp -d /var/backups/live-infinita-mvp010.XXXXXX)
chmod 700 "$backup"
echo "Backup: $backup"
cp -p "$runtime" "$backup/old-main.py"
cp -p "$bridge" "$backup/old-tiktok-live-bridge.py"
tar -C /var/lib -czf "$backup/data-before-update.tar.gz" live-infinita

stopped=0
changed=0
recover() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    echo 'Verificação falhou; restaurando MVP-009.' >&2
    systemctl stop live-infinita || true
    systemctl disable --now live-infinita-integrations.path || true
    if [[ $changed -eq 1 ]]; then
      cp -p "$backup/old-main.py" "$runtime"
      cp -p "$backup/old-tiktok-live-bridge.py" "$bridge"
      rm -f "$path_unit" "$reload_unit"
      rm -rf "$install_dir/apps/integrations" "$install_dir/apps/manager"
      rm -f "$install_dir/deploy/reload-integrations.sh"
      systemctl daemon-reload || true
    fi
    systemctl start live-infinita || true
    echo "Dados preservados; backup em $backup" >&2
  fi
  exit "$result"
}
trap recover EXIT
stopped=1
systemctl stop live-infinita
changed=1
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/world-runtime/main.py" "$runtime"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/sources/tiktok_live_bridge.py" "$bridge"
install -d -o liveinfinita -g liveinfinita -m 0755 "$install_dir/apps/integrations" "$install_dir/apps/manager"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/integrations/settings.py" "$install_dir/apps/integrations/settings.py"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/index.html" "$install_dir/apps/manager/index.html"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/style.css" "$install_dir/apps/manager/style.css"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/app.js" "$install_dir/apps/manager/app.js"
install -o root -g root -m 0755 "$source_dir/deploy/reload-integrations.sh" "$install_dir/deploy/reload-integrations.sh"
install -o root -g root -m 0644 "$source_dir/deploy/live-infinita-integrations.path" "$path_unit"
install -o root -g root -m 0644 "$source_dir/deploy/live-infinita-integrations-reload.service" "$reload_unit"
check_hash 56fc90e7e5949d7433870122edbb8ad08352333c6f42457eba8507199c079864 "$runtime"
check_hash cf6c3f4662cee37f0dff0b6bdd38b42ecb4db2c0a31265d9ca61fdc2cdc68c45 "$bridge"
systemctl daemon-reload
systemctl enable --now live-infinita-integrations.path
systemctl start live-infinita

"$python" - <<'PY'
import json, time, urllib.error, urllib.request
base='http://127.0.0.1:8080'
def get(path):
    with urllib.request.urlopen(base+path, timeout=10) as r:
        return r.status, r.read()
for attempt in range(30):
    try:
        _, raw=get('/api/health'); health=json.loads(raw); break
    except OSError:
        if attempt == 29: raise
        time.sleep(1)
assert (health['mvp'],health['version']) == ('010','0.11.0'), health
assert health['integration_management_enabled'] and health['replay_ok'], health
assert json.loads(get('/api/replay/verify')[1])['ok']
status,page=get('/manage/')
assert status == 200 and b'Ger\xc3\xaancia' in page
try:
    get('/api/manage/integrations')
    raise AssertionError('Gerência permitiu leitura sem chave')
except urllib.error.HTTPError as exc:
    assert exc.code == 401, exc.code
print('MVP-010 validado: painel, proteção, health e replay OK.')
PY
systemctl is-active --quiet live-infinita
systemctl is-active --quiet live-infinita-integrations.path
echo 'MVP-010 online. Nginx, Godot e segredos existentes preservados.'
