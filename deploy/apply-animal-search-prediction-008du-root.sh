#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
REPO=/home/etbra/live.infinita
RUNTIME=/opt/live.infinita/apps/world-runtime
SERVICE=live-infinita-animal-search.service
TIMER=live-infinita-animal-search.timer
PRIVATE=/var/lib/live-infinita/wildlife/search-predictions.json
PUBLIC=/var/www/live-infinita-godot/wildlife/search-predictions.json
cd "$REPO"
[ -z "$(git status --porcelain)" ] || { echo '008DU_ABORT checkout precisa estar limpo'; exit 3; }
[ -f "$RUNTIME/nov_animal_memory_sync.py" ]
[ -f /var/lib/live-infinita/wildlife/encounters.json ]
[ -f /var/lib/live-infinita/wildlife/encounters-ack.json ]
systemctl is-active --quiet live-infinita-animal-memory.timer
LOG=/home/etbra/008du-animal-search-rollout.log
touch "$LOG"; chown etbra:etbra "$LOG"; chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
SHA="$(git rev-parse --short HEAD)"
echo "008DU_START source=$SHA"
BACKUP="/opt/live.infinita/.rollouts/008du-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
FILES=("$RUNTIME/nov_animal_search_prediction.py" "/etc/systemd/system/$SERVICE" "/etc/systemd/system/$TIMER" "$PRIVATE" "$PUBLIC")
WAS_ENABLED=0
if systemctl is-enabled --quiet "$TIMER" 2>/dev/null; then WAS_ENABLED=1; fi
for i in "${!FILES[@]}"; do
  [ ! -L "${FILES[$i]}" ] || { echo '008DU_ABORT destino é link simbólico'; exit 4; }
  if [ -f "${FILES[$i]}" ]; then cp -a "${FILES[$i]}" "$BACKUP/$i"; fi
done
rollback() {
  rc=$?; trap - ERR
  echo "008DU_ROLLBACK rc=$rc"
  systemctl disable --now "$TIMER" || true
  systemctl stop "$SERVICE" || true
  for i in "${!FILES[@]}"; do
    if [ -f "$BACKUP/$i" ]; then cp -a "$BACKUP/$i" "${FILES[$i]}"; else rm -f "${FILES[$i]}"; fi
  done
  systemctl daemon-reload
  if [ "$WAS_ENABLED" -eq 1 ]; then systemctl enable --now "$TIMER" || true; fi
  echo 'Renderer, animais, encontros observados e memórias da Memoria.ia não foram alterados.'
  exit "$rc"
}
trap rollback ERR
systemctl stop "$TIMER" 2>/dev/null || true
systemctl stop "$SERVICE" 2>/dev/null || true
install -o liveinfinita -g liveinfinita -m 0664 "$REPO/apps/world-runtime/nov_animal_search_prediction.py" "$RUNTIME/nov_animal_search_prediction.py"
for f in "$SERVICE" "$TIMER"; do install -o root -g root -m 0644 "$REPO/deploy/$f" "/etc/systemd/system/$f"; done
systemctl daemon-reload
systemd-analyze verify "/etc/systemd/system/$SERVICE" "/etc/systemd/system/$TIMER"
READY=0
for attempt in {1..10}; do
  systemctl start "$SERVICE"
  if python3 - <<'CHECK'
import json,time,pathlib,hashlib
public=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-predictions.json')
private=pathlib.Path('/var/lib/live-infinita/wildlife/search-predictions.json')
s=json.loads(public.read_text())
assert s['schema']=='live-infinita-nov-animal-search/v1'
assert s['last_error'] is None
assert time.time()-s['generated_at_unix']<30
assert s['decision_use'] is False and s['world_write_authority'] is False
assert s['contains_prediction'] is True and s['absence_claim'] is False
assert private.stat().st_mode & 0o777 == 0o600
assert public.stat().st_mode & 0o777 == 0o644
envelope=json.loads(private.read_text())
assert envelope['sha256']==hashlib.sha256(envelope['payload'].encode()).hexdigest()
print('008DU_FORECAST_OK',s['reason'],'forecasts',len(s['forecasts']),'paired',s['counters']['paired'])
CHECK
  then READY=1; break; fi
  sleep 1
done
[ "$READY" -eq 1 ]
systemctl enable --now "$TIMER"
systemctl is-active --quiet "$TIMER"
systemctl is-active --quiet live-infinita-renderer.service
python3 - <<'CHECK'
import json,time,urllib.request
with urllib.request.urlopen('https://live.etbra.com.br/godot/wildlife/search-predictions.json?t='+str(time.time()),timeout=20) as r:s=json.load(r)
assert s['schema']=='live-infinita-nov-animal-search/v1' and s['last_error'] is None
assert time.time()-s['generated_at_unix']<30
assert s['decision_use'] is False and s['contains_prediction'] is True
print('008DU_PUBLIC_OK',s['reason'])
CHECK
echo "008DU_OK source=$SHA backup=$BACKUP"
echo 'Previsões em avaliação: aguardam recorrência suficiente; a caminhada permanece sob o controlador atual.'
