#!/usr/bin/env bash
set -Eeuo pipefail
[ "$EUID" -eq 0 ] || { echo "Execute com sudo"; exit 2; }
REPO=/home/etbra/live.infinita
WEB=/var/www/live-infinita-godot
cd "$REPO"
LOG=/home/etbra/008ca-rollout.log
touch "$LOG"
chown etbra:etbra "$LOG"
chmod 0644 "$LOG"
exec > >(tee -a "$LOG") 2>&1
echo "008CA_START"
if [ -n "$(git status --porcelain)" ]; then
  echo "008CA_ABORT: existem alterações locais."
  git status --short
  exit 3
fi
test -s "$WEB/world-map-preview/index.html"
test -s "$WEB/index.html"
python3 - "$WEB" <<'PY'
import json,sys,urllib.request
from pathlib import Path
web=Path(sys.argv[1])
b=json.loads((web/"world-map-preview/build.json").read_text())
assert b.get("nov_smooth_locomotion") is True, "008BZ ainda não publicada"
assert b.get("nov_procedural_gait") is True
with urllib.request.urlopen("https://live.etbra.com.br/godot/world-map-preview/build.json",timeout=20) as r:
    assert json.load(r)["source_commit"] == b["source_commit"]
with urllib.request.urlopen("http://127.0.0.1:8080/api/health",timeout=10) as r:
    assert json.load(r)["ok"] is True
print("008CA_READY_WORLD",b["source_commit"])
PY
BACKUP="/opt/live.infinita/.rollouts/008ca-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$BACKUP"
cp -a "$WEB/index.html" "$BACKUP/index.html"
cp -a "$WEB/build.json" "$BACKUP/build.json"
rollback() {
  rc=$?
  trap - ERR
  install -o www-data -g www-data -m 0644 "$BACKUP/index.html" "$WEB/index.html"
  install -o www-data -g www-data -m 0644 "$BACKUP/build.json" "$WEB/build.json"
  echo "ROLLBACK 008CA rc=$rc" >&2
  exit "$rc"
}
trap rollback ERR
install -o www-data -g www-data -m 0644 "$REPO/apps/renderer-godot/live-entrypoint.html" "$WEB/.index-008ca.html"
python3 - "$WEB" <<'PY'
import json,sys
from pathlib import Path
web=Path(sys.argv[1])
b=json.loads((web/"world-map-preview/build.json").read_text())
b["live_entrypoint"]="/godot/"
b["live_target"]="/godot/world-map-preview/"
b["entrypoint_release"]="008CA"
(web/".build-008ca.json").write_text(json.dumps(b,ensure_ascii=False,indent=2)+"\n")
PY
chown www-data:www-data "$WEB/.build-008ca.json"
chmod 0644 "$WEB/.build-008ca.json"
mv -f "$WEB/.index-008ca.html" "$WEB/index.html"
mv -f "$WEB/.build-008ca.json" "$WEB/build.json"
python3 - <<'PY'
import json,urllib.request
with urllib.request.urlopen("https://live.etbra.com.br/godot/?entrypoint-check=008ca",timeout=20) as r:
    html=r.read().decode()
assert "window.location.replace(target.href)" in html
assert 'new URL("/godot/world-map-preview/"' in html
with urllib.request.urlopen("https://live.etbra.com.br/godot/build.json",timeout=20) as r:
    b=json.load(r)
assert b["entrypoint_release"] == "008CA"
assert b["nov_smooth_locomotion"] is True
print("008CA_PUBLIC_OK",b["source_commit"],b["live_target"])
PY
trap - ERR
echo "008CA_OK backup=$BACKUP"
echo "Recarregue a fonte de navegador/monitor em https://live.etbra.com.br/godot/"
