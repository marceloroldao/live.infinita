#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008CH_INGEST_ABORT alterações locais'; exit 3; }
LOG=/home/etbra/008ch-ingest-fix.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "008CH_INGEST_START source=$(git rev-parse --short HEAD)"
SOURCE='/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-navigation-episodes-008ch.json'
test -s "$SOURCE"
systemctl is-active --quiet live-infinita-renderer.service
# Clear timed-out requests before installing the compact evidence bridge.
# No database, node or episode is deleted.
restore_timer() { systemctl start live-infinita-nov-navigation-memory-sync.timer || true; }
trap restore_timer EXIT
systemctl stop live-infinita-nov-navigation-memory-sync.timer
systemctl stop live-infinita-nov-navigation-memory-sync.service
systemctl restart live-infinita-memoria-local.service
systemctl is-active --quiet live-infinita-memoria-local.service
python3 - <<'WAIT_API'
import time,urllib.request,urllib.error
for attempt in range(60):
 try:
  urllib.request.urlopen("http://127.0.0.1:8788/health",timeout=1).close()
  break
 except urllib.error.HTTPError:
  break # An HTTP response proves the application finished startup.
 except (OSError,urllib.error.URLError):
  if attempt % 10 == 0:print("Aguardando API local",flush=True)
  time.sleep(1)
else:raise SystemExit("Memoria local não terminou a inicialização")
WAIT_API
bash "$REPO/deploy/apply-navigation-memory-bridge-008ce-root.sh"
python3 - <<'PY'
from pathlib import Path
import json,gzip
root=Path('/var/lib/live-infinita/memoria-local')
state=json.loads((root/'navigation-episodes.checkpoint.json').read_text())
assert state['confirmed'] > 0
assert state['last_observation_id'].startswith('structural-event:')
archives=list((root/'navigation-episodes').glob('*.json.gz'))
assert archives
for p in archives:
 with gzip.open(p,'rb') as f:
  raw=f.read(2000001)
 assert len(raw)<=2000000
 row=json.loads(raw)
 assert row['episode_id'].replace(':','-')+'.json.gz' == p.name
print('008CH_EPISODE_DURABLE_ACK_OK confirmed=',state['confirmed'],'archives=',len(archives))
PY
systemctl is-active --quiet live-infinita-nov-navigation-memory-sync.timer
systemctl is-active --quiet live-infinita-renderer.service
trap - EXIT
echo '008CH_INGEST_OK'
