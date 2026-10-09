#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo 'Execute com sudo'; exit 2; }
case "${1:-}" in on) FLAG=1;; off) FLAG=0;; *) echo 'Uso: set-failure-preference-008fa-root.sh on|off'; exit 2;; esac
grep -q 'LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE' /opt/live.infinita/apps/renderer-godot/nov_navigation_pattern_collector.gd || { echo 'Aplique a 008FA primeiro'; exit 3; }
DIR=/etc/systemd/system/live-infinita-renderer.service.d
FILE="$DIR/99-navigation-failure-preference-008fa.conf"
BACKUP="/opt/live.infinita/.rollouts/008fa-switch-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP" "$DIR"
if [ -f "$FILE" ]; then cp -a "$FILE" "$BACKUP/failure-preference.conf"; fi
rollback() {
  rc=$?; trap - ERR
  if [ -f "$BACKUP/failure-preference.conf" ]; then install -m 0644 "$BACKUP/failure-preference.conf" "$FILE"; else rm -f "$FILE"; fi
  systemctl daemon-reload || true
  systemctl restart live-infinita-renderer.service || true
  echo "008FA_SWITCH_ROLLBACK rc=$rc"
  exit "$rc"
}
trap rollback ERR
printf '[Service]\nEnvironment=LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE=%s\n' "$FLAG" > "$FILE"
systemctl daemon-reload
RESTART_AT="$(date +%s)"
systemctl restart live-infinita-renderer.service
python3 - "$FLAG" "$RESTART_AT" <<'CHECK'
import pathlib,json,time,sys
p=pathlib.Path('/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-learning-status-008df.json')
expected=sys.argv[1]=='1'
for _ in range(60):
    try:
        d=json.loads(p.read_text())
        if d.get('observed_at_unix',0)>=int(sys.argv[2]) and d.get('patterns',{}).get('failure_preference_enabled') is expected:
            print('008FA_SWITCH_OK',{'failure_preference_enabled':expected,'ram_records':d['patterns']['ram_records']})
            break
    except (OSError,ValueError,KeyError):
        pass
    time.sleep(1)
else:
    raise RuntimeError('Renderer não confirmou a configuração; restauração automática')
CHECK
systemctl is-active --quiet live-infinita-renderer.service
echo 'Histórico de memória preservado.'
