#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
case "${1:-}" in on) FLAG=1;; off) FLAG=0;; *) echo 'Uso: set-animal-approach-008fb-root.sh on|off'; exit 2;; esac
grep -q 'LIVE_INFINITA_ANIMAL_APPROACH_ENABLED' /opt/live.infinita/apps/renderer-godot/nov_animal_search_intent.gd || { echo 'Aplique a 008FB primeiro'; exit 3; }
DIR=/etc/systemd/system/live-infinita-renderer.service.d
FILE="$DIR/99-animal-approach-008fb.conf"
BACKUP="/opt/live.infinita/.rollouts/008fb-switch-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP" "$DIR"
if [ -f "$FILE" ]; then cp -a "$FILE" "$BACKUP/animal-approach.conf"; fi
rollback() {
  rc=$?; trap - ERR
  if [ -f "$BACKUP/animal-approach.conf" ]; then install -m 0644 "$BACKUP/animal-approach.conf" "$FILE"; else rm -f "$FILE"; fi
  systemctl daemon-reload || true
  systemctl restart live-infinita-renderer.service || true
  echo "008FB_SWITCH_ROLLBACK rc=$rc"
  exit "$rc"
}
trap rollback ERR
printf '[Service]\nEnvironment=LIVE_INFINITA_ANIMAL_APPROACH_ENABLED=%s\n' "$FLAG" > "$FILE"
systemctl daemon-reload
RESTART_AT="$(python3 -c 'import time; print(time.time())')"
systemctl restart live-infinita-renderer.service
python3 - "$FLAG" "$RESTART_AT" <<'CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/var/www/live-infinita-godot/wildlife/search-intent.json')
expected=sys.argv[1]=='1'
for _ in range(60):
    try:
        d=json.loads(p.read_text())
        if d.get('generated_at_unix',0)>=float(sys.argv[2]) and d.get('approach',{}).get('enabled') is expected:
            print('008FB_SWITCH_OK',{'animal_approach_enabled':expected})
            break
    except (OSError,ValueError,KeyError):
        pass
    time.sleep(1)
else:
    raise RuntimeError('Renderer não confirmou a configuração; restauração automática')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
echo 'Histórico de memória preservado.'
