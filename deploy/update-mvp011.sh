#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/update-mvp011.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
install_dir=/opt/live.infinita
runtime=$install_dir/apps/world-runtime/main.py
manager=$install_dir/apps/manager
renderer=$install_dir/apps/renderer-web/index.html
nginx_site=/etc/nginx/sites-available/live-infinita

check_hash() { printf '%s  %s\n' "$1" "$2" | sha256sum --check --status; }
check_hash 3f5659b76c44886edc490c91c58b4ed67ca76944e71af941446ce005f0b2997e "$runtime"
check_hash e6a16be3a48ad13fb7b7f18397fad8f06c8d776b8d2b7590cd80f7149e84528d "$manager/index.html"
check_hash 1507c38077bbea57d2df9215b8dcb9f0b7ae4fe71cfae8ab2e4d464351899635 "$manager/style.css"
check_hash c7a165058ff78039c8a9741c5f091d6745a8f4dd3e94a93e41fba21a016d51dc "$manager/app.js"
check_hash 6d73bde58a1dbceb465d64fa4d6ddbcda51d7f8064fc26afc394a9571efa8f86 "$renderer"
check_hash c031f74de02016d4fb9a04cfb2b277ee4980fec15ffca7bcafb257a26db7e6b0 "$nginx_site"
systemctl is-active --quiet live-infinita
test -f /var/www/live-infinita-godot/index.html

backup=$(mktemp -d /var/backups/live-infinita-mvp011.XXXXXX)
chmod 700 "$backup"
echo "Backup: $backup"
cp -p "$runtime" "$backup/main.py"
cp -p "$manager/index.html" "$backup/manager-index.html"
cp -p "$manager/style.css" "$backup/manager-style.css"
cp -p "$manager/app.js" "$backup/manager-app.js"
cp -p "$renderer" "$backup/renderer-index.html"
cp -p "$nginx_site" "$backup/nginx-live-infinita"
tar -C /var/lib -czf "$backup/data-before-update.tar.gz" live-infinita

changed=0
recover() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $changed -eq 1 ]]; then
    echo 'Verificação falhou; restaurando MVP-010.' >&2
    systemctl stop live-infinita || true
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/main.py" "$runtime"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/manager-index.html" "$manager/index.html"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/manager-style.css" "$manager/style.css"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/manager-app.js" "$manager/app.js"
    install -o liveinfinita -g liveinfinita -m 0644 "$backup/renderer-index.html" "$renderer"
    install -o root -g root -m 0644 "$backup/nginx-live-infinita" "$nginx_site"
    nginx -t && systemctl reload nginx || true
    systemctl start live-infinita || true
    echo "Dados e segredos preservados; backup em $backup" >&2
  fi
  exit "$result"
}
trap recover EXIT

systemctl stop live-infinita
changed=1
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/world-runtime/main.py" "$runtime"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/index.html" "$manager/index.html"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/style.css" "$manager/style.css"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/manager/app.js" "$manager/app.js"
install -o liveinfinita -g liveinfinita -m 0644 "$source_dir/apps/renderer-web/index.html" "$renderer"
install -o root -g root -m 0644 "$source_dir/deploy/nginx-live-infinita.conf" "$nginx_site"
nginx -t
systemctl start live-infinita
systemctl reload nginx

"$install_dir/.venv/bin/python" - <<'PY'
import json, time, urllib.error, urllib.request
base='http://127.0.0.1:8080'
def get(path):
    with urllib.request.urlopen(base+path, timeout=10) as response:
        return response.status, response.read()
for attempt in range(30):
    try:
        _, raw=get('/api/health'); health=json.loads(raw); break
    except OSError:
        if attempt == 29: raise
        time.sleep(1)
assert (health['mvp'],health['version']) == ('011','0.12.0'), health
assert health['integration_management_enabled'] and health['replay_ok'], health
status,page=get('/')
assert status == 200 and b'login-form' in page and b'/godot/' in page and b'/gdscript/' in page
status,gdscript=get('/gdscript/')
assert status == 200 and b'/gdscript/app.js' in gdscript
try:
    get('/api/manage/integrations')
    raise AssertionError('Gerência permitiu leitura sem login')
except urllib.error.HTTPError as exc:
    assert exc.code == 401, exc.code
print('MVP-011 validado: login, manager principal, GDScript e replay OK.')
PY
curl --fail --silent --show-error http://127.0.0.1/godot/ >/dev/null
systemctl is-active --quiet live-infinita
echo 'MVP-011 online. Godot, dados e segredos preservados.'
