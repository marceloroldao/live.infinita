#!/usr/bin/env bash
# MVP-018D — one-shot private mirror proof. Never alters runtime or production DB.
set -Eeuo pipefail
REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
MEMORIA_SHA=cf699e2daf8f91a97f05892abd58890f11c4acbe
BDR_SHA=317882a00f041fc1568ff986af8016b09453f21a
CODE_ROOT="/opt/live-infinita-bdr-mirror/$MEMORIA_SHA"
LIB="$CODE_ROOT/libbdr_atomic_c_api.so"
DATA=/var/lib/live-infinita/memoria-local
SOURCE="$DATA/external-episodes-incremental/external-episodes.sqlite3"
WORLD=live-infinita-autonomous-world.service
MEMORY=live-infinita-memoria-local.service
RENDERER=live-infinita-renderer.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
TIMER=live-infinita-memoria-nov-sync.timer
fail(){ echo "MVP018D_BDR_MIRROR_BLOCKED: $*" >&2; exit 2; }
(( EUID != 0 )) || fail "execute como etbra, não como root"
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail "fora da main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "checkout sujo"
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail "atualize a main"
bash -n deploy/mvp018d-bdr-read-only-mirror.sh
for svc in "$WORLD" "$MEMORY" "$RENDERER" "$API" "$AUDIO" "$RELAY" "$TIMER"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
memory_pid="$(systemctl show "$MEMORY" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
relay_pid="$(systemctl show "$RELAY" -p MainPID --value)"
curl -fsS --max-time 8 http://127.0.0.1:8788/api/v1/storage/health |
    "$INSTALL/.venv/bin/python" -c '
import json,sys
d=json.load(sys.stdin)
assert d["backend"]=="sqlite"
assert d["external_episode_persistence"]=="sqlite-incremental"
assert d["external_episode_observations"]>0
print("MVP018D_SOURCE_HEALTH_OK",d["external_episode_observations"])
'
free_bytes="$(df -PB1 "$DATA" | awk 'END{print $4}')"
[[ "$free_bytes" =~ ^[0-9]+$ ]] && (( free_bytes > 1073741824 )) ||
    fail "reserva mínima de 1 GiB indisponível"
stage="$(mktemp -d /tmp/mvp018d-build.XXXXXXXX)"
trap 'rm -rf -- "$stage"' EXIT

# Immutable upstream versions; Ubuntu keeps its runtime package set unchanged.
git clone -q --filter=blob:none --depth 1 \
    https://github.com/marceloroldao/memoria.ia.git "$stage/memoria"
git -C "$stage/memoria" fetch -q --depth 1 origin "$MEMORIA_SHA"
git -C "$stage/memoria" checkout -q --detach "$MEMORIA_SHA"
[[ "$(git -C "$stage/memoria" rev-parse HEAD)" == "$MEMORIA_SHA" ]] ||
    fail "pin Memoria.ia divergente"
git clone -q --filter=blob:none --depth 1 --branch v1.2.0-rc4 \
    https://github.com/marceloroldao/resolutive-DB.git "$stage/bdr"
[[ "$(git -C "$stage/bdr" rev-parse HEAD)" == "$BDR_SHA" ]] ||
    fail "pin BDR divergente"
mkdir -m 0700 "$stage/zlib"
(
  cd "$stage/zlib"
  apt-get download zlib1g-dev >/dev/null
  deb="$(find . -maxdepth 1 -name 'zlib1g-dev*.deb' -print -quit)"
  [[ -f "$deb" ]] || fail "zlib1g-dev indisponível para extração privada"
  dpkg-deb -x "$deb" extracted
)
[[ -f "$stage/zlib/extracted/usr/include/zlib.h" ]] ||
    fail "cabeçalhos zlib ausentes"
base="$stage/bdr/experimental/api_v86"
nice -n 15 g++ -std=c++17 -O2 -fPIC -shared \
    -I "$stage/zlib/extracted/usr/include" -I "$base/include" \
    "$base/src/atomic_c_api.cpp" "$base/src/database_v1.cpp" \
    "$stage/bdr/experimental/api_v111/atomic_database.cpp" \
    "$stage/bdr/experimental/api_v110/durable_database.cpp" \
    "$stage/bdr/experimental/api_v106/migration.cpp" \
    "$stage/bdr/experimental/api_v102/file_wal.cpp" \
    "$stage/bdr/experimental/api_v101/atomic_wal.cpp" \
    -pthread /usr/lib/x86_64-linux-gnu/libz.so.1 \
    -o "$stage/libbdr_atomic_c_api.so"
[[ -s "$stage/libbdr_atomic_c_api.so" ]] || fail "compilação BDR falhou"
MVP018D_SCRATCH="$stage" \
PYTHONPATH="$stage/memoria/src:$stage/bdr" \
BDR_ATOMIC_LIBRARY="$stage/libbdr_atomic_c_api.so" \
"$INSTALL/.venv/bin/python" deploy/mvp018d-bdr-native-preflight.py

# Only now may the authorized operator install auxiliary code, no service changes.
sudo -v
sudo test -f "$SOURCE" || fail "journal SQLite ausente"
sudo test ! -L "$SOURCE" || fail "journal SQLite é symlink"
sudo test ! -e "$CODE_ROOT" || fail "código auxiliar já presente nesta versão"
sudo install -d -o root -g root -m 0755 "$CODE_ROOT"
sudo cp -a "$stage/memoria/src/memoria_resolutiva" "$CODE_ROOT/"
sudo cp -a "$stage/bdr/bdr" "$CODE_ROOT/"
sudo install -o root -g root -m 0755 \
    "$stage/memoria/scripts/mirror_external_episodes_to_bdr.py" \
    "$CODE_ROOT/mirror_external_episodes_to_bdr.py"
sudo install -o root -g root -m 0755 "$stage/libbdr_atomic_c_api.so" "$LIB"
sudo chown -R root:root "$CODE_ROOT"
sudo chmod -R go-w "$CODE_ROOT"
parent="$DATA/bdr-mirror-runs"
sudo install -d -o liveinfinita -g liveinfinita -m 0700 "$parent"
output="$parent/$(date -u +%Y%m%dT%H%M%SZ)-$$"
sudo test ! -e "$output" || fail "saída já existe"

# Runs as memory owner; input is mode=ro SQLite online backup, with WAL.
sudo -u liveinfinita env PYTHONPATH="$CODE_ROOT" BDR_ATOMIC_LIBRARY="$LIB" \
    nice -n 15 timeout 180 "$INSTALL/.venv/bin/python" \
    "$CODE_ROOT/mirror_external_episodes_to_bdr.py" \
    --source-sqlite "$SOURCE" --output-directory "$output" \
    --bdr-library "$LIB" --max-records 10000
sudo -u liveinfinita "$INSTALL/.venv/bin/python" - "$output/report.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); report=json.loads(p.read_text())
assert p.stat().st_mode&0o777==0o600
assert report["source_snapshot_records"]>0
assert report["source_snapshot_records"]==report["inserted_into_bdr"]
assert report["verified_cold_restart"] and report["verified_idempotent_replay"]
assert not report["backend_cutover"] and not report["production_checkpoint_advanced"]
assert not report["world_mutated"] and not report["central_sync"]
print("MVP018D_MIRROR_REPORT_VERIFIED",report["source_snapshot_records"],
      report["record_manifest_sha256"][:16],report["bdr_durable_sequence"])
PY
check_pid(){
    systemctl is-active --quiet "$1" || fail "$1 inativo"
    [[ "$(systemctl show "$1" -p MainPID --value)" == "$2" ]] ||
        fail "$1 reiniciou inesperadamente"
}
check_pid "$WORLD" "$world_pid"
check_pid "$MEMORY" "$memory_pid"
check_pid "$RENDERER" "$renderer_pid"
check_pid "$API" "$api_pid"
check_pid "$AUDIO" "$audio_pid"
check_pid "$RELAY" "$relay_pid"
systemctl is-active --quiet "$TIMER" || fail "timer local inativo"
curl -fsS --max-time 8 http://127.0.0.1:8788/api/v1/storage/health |
    "$INSTALL/.venv/bin/python" -c '
import json,sys
d=json.load(sys.stdin)
assert d["external_episode_persistence"]=="sqlite-incremental"
print("MVP018D_LIVE_SQLITE_STILL_AUTHORITATIVE",d["external_episode_observations"])
'
echo "MVP018D_BDR_READ_ONLY_MIRROR_OK output=$output"
echo "MVP018D_NO_CUTOVER world_pid=$world_pid memory_pid=$memory_pid"
