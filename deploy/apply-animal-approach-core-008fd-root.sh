#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
DST=/opt/live.infinita/apps/world-runtime
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008FD_ABORT checkout precisa estar limpo'; exit 3; }
systemctl is-active --quiet live-infinita-renderer.service
systemctl is-active --quiet live-infinita-memoria-local.service
cmp apps/renderer-godot/nov_animal_approach_history.gd /opt/live.infinita/apps/renderer-godot/nov_animal_approach_history.gd
SOURCE=/var/lib/live-infinita/wildlife/search-policy.json.approach
[ -f "$SOURCE" ] && [ ! -L "$SOURCE" ]
LOG=/home/etbra/008fd-animal-approach-core-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
BACKUP="/opt/live.infinita/.rollouts/008fd-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
echo "008FD_START source=$SHA"
MODULE=nov_animal_approach_sync.py
SERVICE=live-infinita-animal-approach.service
TIMER=live-infinita-animal-approach.timer
WAS_ENABLED=0
if systemctl is-enabled --quiet "$TIMER" 2>/dev/null; then WAS_ENABLED=1; fi
if [ -f "$DST/$MODULE" ]; then cp -a "$DST/$MODULE" "$BACKUP/$MODULE"; fi
for unit in "$SERVICE" "$TIMER"; do
  if [ -f "/etc/systemd/system/$unit" ]; then cp -a "/etc/systemd/system/$unit" "$BACKUP/$unit"; fi
done
PUBLIC=/var/www/live-infinita-godot/wildlife/approach-core.json
if [ -f "$PUBLIC" ]; then cp -a "$PUBLIC" "$BACKUP/approach-core.json"; fi
rollback() {
  rc=$?; trap - ERR
  echo "008FD_ROLLBACK rc=$rc"
  systemctl disable --now "$TIMER" || true
  systemctl stop "$SERVICE" || true
  for unit in "$SERVICE" "$TIMER"; do
    if [ -f "$BACKUP/$unit" ]; then install -m 0644 "$BACKUP/$unit" "/etc/systemd/system/$unit"; else rm -f "/etc/systemd/system/$unit"; fi
  done
  if [ -f "$BACKUP/$MODULE" ]; then install -o liveinfinita -g liveinfinita -m 0664 "$BACKUP/$MODULE" "$DST/$MODULE"; else rm -f "$DST/$MODULE"; fi
  if [ -f "$BACKUP/approach-core.json" ]; then install -o liveinfinita -g liveinfinita -m 0644 "$BACKUP/approach-core.json" "$PUBLIC"; else rm -f "$PUBLIC"; fi
  systemctl daemon-reload || true
  if [ "$WAS_ENABLED" = 1 ]; then systemctl enable --now "$TIMER" || true; fi
  echo 'Fatos confirmados no núcleo, histórico e checkpoints preservados.'
  exit "$rc"
}
trap rollback ERR
systemctl stop "$TIMER" 2>/dev/null || true
systemctl stop "$SERVICE" 2>/dev/null || true
install -o liveinfinita -g liveinfinita -m 0664 "apps/world-runtime/$MODULE" "$DST/$MODULE"
for unit in "$SERVICE" "$TIMER"; do install -m 0644 "deploy/$unit" "/etc/systemd/system/$unit"; done
systemctl daemon-reload
RESTART_AT="$(python3 -c 'import time; print(time.time())')"
systemctl enable --now "$TIMER"
# Up to four measured records per execution; each ACK is checkpointed.
systemctl start "$SERVICE"
systemctl start "$SERVICE"
[ "$(systemctl show "$SERVICE" -p Result --value)" = success ]
systemctl is-active --quiet "$TIMER"
python3 - "$RESTART_AT" <<'CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/approach-core.json')
for _ in range(30):
    try:
        d=json.loads(p.read_text())
        if isinstance(d,dict) and isinstance(d.get('generated_at_unix'),(int,float)) and d['generated_at_unix']>=float(sys.argv[1]) and -5<time.time()-d['generated_at_unix']<15 and d.get('schema')=='live-infinita-animal-approach-core-status/v1' and d.get('source')=='memoria.ia-local-structural-api' and d.get('world_write_authority') is False and d.get('decision_use') is False and d.get('learned_hunting') is False and d.get('capture') is False:
            for key in ('confirmed_total','cached_recovered','eligible_in_source'):
                assert type(d.get(key)) is int and d[key]>=0
            assert d['eligible_in_source']==0 or d['confirmed_total']>0 and d['cached_recovered']>0
            print('008FD_CORE_READY',json.dumps(d,sort_keys=True))
            break
    except (OSError,ValueError,AssertionError):
        pass
    time.sleep(1)
else:
    raise RuntimeError('Núcleo não publicou recuperação recente das aproximações')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
echo "008FD_OK source=$SHA backup=$BACKUP"
echo 'Resultados medidos sincronizados com a Memoria.ia; estratégia de aproximação preservada.'
