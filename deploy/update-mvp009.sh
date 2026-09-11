#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Execute com sudo bash deploy/update-mvp009.sh'; exit 1; }
source_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
runtime=/opt/live.infinita/apps/world-runtime/main.py
binding=/opt/live.infinita/apps/actors/bindings.py
helper=/opt/live.infinita/deploy/manage-actor.py
config=/etc/live-infinita/operator.env
dropin=/etc/systemd/system/live-infinita.service.d/009-actor-operator.conf
python=/opt/live.infinita/.venv/bin/python

check_hash() { printf '%s  %s\n' "$1" "$2" | sha256sum --check --status; }
check_hash 8ff5baa22c636fe5bc1fabba4dca22feb92fa6f73d77951d753c74a12bba6135 "$runtime"
check_hash 2f26a27cea8535ec4114ddd76cc644ede6fd38892e32164b963c9c521a1c40e4 /opt/live.infinita/apps/actors/store.py
for path in "$binding" "$helper" "$config" "$dropin"; do
  [[ ! -e "$path" && ! -L "$path" ]] || { echo "Arquivo já existe: $path; atualização cancelada."; exit 1; }
done
systemctl is-active --quiet live-infinita
"$python" - <<'PY'
import json, urllib.request
with urllib.request.urlopen('http://127.0.0.1:8080/api/replay/verify', timeout=15) as r:
    assert json.load(r)['ok'], 'Replay inconsistente antes da atualização'
PY

backup=$(mktemp -d /var/backups/live-infinita-mvp009.XXXXXX)
chmod 700 "$backup"
echo "Backup: $backup"
install -m 0644 "$source_dir/apps/world-runtime/main.py" "$backup/new-main.py"
install -m 0644 "$source_dir/apps/actors/bindings.py" "$backup/new-bindings.py"
install -m 0644 "$source_dir/deploy/manage-actor.py" "$backup/new-helper.py"
check_hash fac30074d2d5293ffa956781c539b12026cdd8a89c019b5ec0562c9dfc068b57 "$backup/new-main.py"
check_hash fe4cd61f874c0e65531226ec7d2b567ae54539bbf9fd310d61236c7f0d4c5cf1 "$backup/new-bindings.py"
check_hash ca84b0222f09c31062bfa4b5625294789cb8b883eeb55a1acfe53de0338491af "$backup/new-helper.py"
cp -p "$runtime" "$backup/old-main.py"

stopped=0
changed=0
recover() {
  result=$?
  trap - EXIT
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    echo 'Verificação falhou; restaurando MVP-008.' >&2
    systemctl stop live-infinita || true
    if [[ $changed -eq 1 ]]; then
      cp -p "$backup/old-main.py" "$runtime"
      rm -f "$binding" "$helper" "$config" "$dropin"
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
tar -C /var/lib -czf "$backup/data-before-update.tar.gz" live-infinita
changed=1
install -o liveinfinita -g liveinfinita -m 0644 "$backup/new-main.py" "$runtime"
install -o liveinfinita -g liveinfinita -m 0644 "$backup/new-bindings.py" "$binding"
install -o root -g root -m 0644 "$backup/new-helper.py" "$helper"
install -d -m 0755 /etc/live-infinita /etc/systemd/system/live-infinita.service.d
"$python" - <<'PY'
import os, secrets
path = '/etc/live-infinita/operator.env'
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, 'w') as f:
    f.write('LIVE_INFINITA_OPERATOR_TOKEN=' + secrets.token_hex(32) + '\n')
PY
printf '[Service]\nEnvironmentFile=/etc/live-infinita/operator.env\n' > "$dropin"
chmod 0644 "$dropin"
systemctl daemon-reload
systemctl start live-infinita
"$python" - <<'PY'
import json, time, urllib.error, urllib.request
base = 'http://127.0.0.1:8080'
def get(path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return json.load(r)
for attempt in range(30):
    try:
        health = get('/api/health')
        break
    except OSError:
        if attempt == 29:
            raise
        time.sleep(1)
assert (health['mvp'], health['version']) == ('009', '0.10.0'), health
assert health['operator_binding_enabled'] and health['replay_ok'], health
assert get('/api/replay/verify')['ok']
get('/api/actors')
req = urllib.request.Request(base + '/api/actors/api/mvp009-check/entity',
    data=b'{"entity_id":"person_01"}', method='PUT', headers={'Content-Type': 'application/json'})
try:
    with urllib.request.urlopen(req, timeout=10) as r:
        raise AssertionError('Vínculo permitiu acesso sem autenticação')
except urllib.error.HTTPError as e:
    assert e.code == 401, e.code
print('MVP-009 validado: vínculo protegido por chave, Actor State e replay OK.')
PY
systemctl is-active --quiet live-infinita
echo 'MVP-009 online. Godot e nginx preservados.'
