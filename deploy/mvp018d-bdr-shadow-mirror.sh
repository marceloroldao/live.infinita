#!/usr/bin/env bash
# MVP-018D: private BDR shadow of local Memoria.ia V2. No backend cutover.
# Run manually as etbra. Builds public pinned native code in a disposable
# scratch directory; only the service account reads the private SQLite source.
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
VENV_PY=/opt/live.infinita/.venv/bin/python
MEMORIA_PIN=4f40da7876ecece3ce30f743d1b7a8382213aaf1
BDR_PIN=317882a00f041fc1568ff986af8016b09453f21a
ZLIB_PIN=51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf
DATA=/var/lib/live-infinita/memoria-local
SOURCE="$DATA/external-episodes-incremental/external-episodes.sqlite3"
CHECKPOINT="$DATA/nov-ingest.checkpoint.json"
MIRRORS="$DATA/bdr-mirrors"
WORLD=live-infinita-autonomous-world.service
CORE=live-infinita-memoria-local.service
TIMER=live-infinita-memoria-nov-sync.timer
RENDERER=live-infinita-renderer.service
API=live-infinita.service

fail(){ echo "MVP018D_BDR_MIRROR_BLOCKED: $*" >&2; exit 2; }
[[ "$(id -un)" == etbra && "$EUID" -ne 0 ]] || fail 'execute como etbra'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'checkout com alterações rastreadas'
for svc in "$WORLD" "$CORE" "$TIMER" "$RENDERER" "$API"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'não compilar o BDR durante transmissão ativa'
fi
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
core_pid="$(systemctl show "$CORE" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
api_pid="$(systemctl show "$API" -p MainPID --value)"

"$VENV_PY" - <<'PY'
from urllib.request import urlopen
import json
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as reply:
    report=json.load(reply)
assert report["external_episode_persistence"]=="sqlite-incremental", report
assert report["backend"]=="sqlite", report
print("MVP018D_SOURCE_MODE_OK records=",report["external_episode_observations"])
PY

stage="$(mktemp -d /tmp/live-bdr-shadow.XXXXXXXX)"
cleanup(){ rm -rf -- "$stage"; }
trap cleanup EXIT
# This temporary location holds only PUBLIC checked-out source and its build,
# never the private observation or its backup. The service owner must be able
# to traverse it during the one-shot mirror command.
chmod 0755 "$stage"
git clone -q --filter=blob:none --depth 1 https://github.com/marceloroldao/memoria.ia.git "$stage/memoria"
git -C "$stage/memoria" fetch -q --depth 1 origin "$MEMORIA_PIN"
git -C "$stage/memoria" checkout -q --detach "$MEMORIA_PIN"
[[ "$(git -C "$stage/memoria" rev-parse HEAD)" == "$MEMORIA_PIN" ]] || fail 'Memoria.ia pin divergente'
git clone -q --filter=blob:none --depth 1 --branch v1.2.0-rc4 \
    https://github.com/marceloroldao/resolutive-DB.git "$stage/bdr"
[[ "$(git -C "$stage/bdr" rev-parse HEAD)" == "$BDR_PIN" ]] || fail 'BDR tag/pin divergente'
[[ -f "$stage/memoria/scripts/mirror_external_episodes_to_bdr.py" ]] || fail 'espelhador V2 ausente'

if command -v cmake >/dev/null 2>&1; then
    cmake_bin="$(command -v cmake)"
else
    # No persistent apt/Ubuntu package is installed.
    "$VENV_PY" -m pip install --quiet --no-input --disable-pip-version-check \
        --target "$stage/cmake-wheel" 'cmake>=3.21,<4'
    cmake_bin="$stage/cmake-wheel/bin/cmake"
    if [[ ! -x "$cmake_bin" ]]; then
        cmake_dir="$(PYTHONPATH="$stage/cmake-wheel" "$VENV_PY" -c 'import cmake; print(cmake.CMAKE_BIN_DIR)')"
        cmake_bin="$cmake_dir/cmake"
    fi
fi
[[ -x "$cmake_bin" ]] || fail 'cmake temporário não está disponível'
command -v g++ >/dev/null || fail 'g++ não disponível'
# Minimal Ubuntu VMs may have libz runtime but not zlib.h/libz.so. Build
# pinned zlib from public source in scratch, without installing apt packages.
zlib_args=()
zlib_libdir=""
if [[ ! -r /usr/include/zlib.h || ! -e /usr/lib/x86_64-linux-gnu/libz.so ]]; then
    git clone -q --filter=blob:none --depth 1 --branch v1.3.1 \
        https://github.com/madler/zlib.git "$stage/zlib-src"
    [[ "$(git -C "$stage/zlib-src" rev-parse HEAD)" == "$ZLIB_PIN" ]] || fail 'zlib source pin divergente'
    "$cmake_bin" -S "$stage/zlib-src" -B "$stage/zlib-build" \
        -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX="$stage/zlib-prefix" \
        -DBUILD_SHARED_LIBS=ON >/dev/null
    nice -n 15 "$cmake_bin" --build "$stage/zlib-build" --parallel 1 >/dev/null
    "$cmake_bin" --install "$stage/zlib-build" >/dev/null
    zlib_lib="$(find "$stage/zlib-prefix" -name libz.so -print -quit)"
    [[ -n "$zlib_lib" ]] || fail 'zlib temporária ausente'
    zlib_libdir="$(dirname "$zlib_lib")"
    zlib_args=(-DZLIB_ROOT="$stage/zlib-prefix" -DCMAKE_BUILD_RPATH="$zlib_libdir")
    chmod -R a+rX "$stage/zlib-prefix"
    echo 'MVP018D_TEMP_ZLIB_OK (sem apt)'
fi
"$cmake_bin" -S "$stage/bdr/experimental/api_v86" -B "$stage/build" \
    -DCMAKE_BUILD_TYPE=Release "${zlib_args[@]}" >/dev/null
nice -n 15 "$cmake_bin" --build "$stage/build" --parallel 1 \
    --target bdr_atomic_c_api_shared >/dev/null
library="$stage/build/libbdr_atomic_c_api.so"
[[ -f "$library" ]] || fail 'biblioteca BDR nativa não gerada'
chmod -R a+rX "$stage/memoria" "$stage/bdr" "$stage/build"
PYTHONPATH="$stage/bdr:$stage/memoria/src" BDR_ATOMIC_LIBRARY="$library" \
    LD_LIBRARY_PATH="$zlib_libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    "$VENV_PY" - <<'PY'
import os, tempfile
from bdr.atomic import AtomicBDR
with tempfile.TemporaryDirectory(prefix="bdr-abi-probe-") as scratch:
    db=AtomicBDR.open(scratch, library_path=os.environ["BDR_ATOMIC_LIBRARY"])
    assert db._lib.bdr_atomic_c_abi_version()==2
    receipt=db.put_many({"probe":b"native-durable"})
    assert receipt.durable and db.durable_sequence()>=receipt.sequence
    assert db.get("probe")==b"native-durable"
    db.close()
print("MVP018D_NATIVE_BDR_ABI_OK")
PY

# Only explicit operator sudo can authorize accessing the private local
# memory. Do not change owner/permissions of the original source or cursor.
sudo -v
sudo -u liveinfinita test -r "$SOURCE" || fail 'fonte SQLite privada inacessível'
sudo -u liveinfinita test -r "$CHECKPOINT" || fail 'checkpoint privado inacessível'
sudo install -d -o liveinfinita -g liveinfinita -m 0700 "$MIRRORS"
output="$MIRRORS/$(date -u +%Y%m%dT%H%M%SZ)-$$"
[[ ! -e "$output" ]] || fail 'destino BDR já existe'
echo 'MVP018D_BDR_PRIVATE_MIRROR_START (backend SQLite continua ativo)'
# No timer stop/restart, no world/renderer service, no central request.
sudo -u liveinfinita env \
    PYTHONPATH="$stage/memoria/src:$stage/bdr" \
    BDR_ATOMIC_LIBRARY="$library" \
    LD_LIBRARY_PATH="$zlib_libdir${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" \
    /usr/bin/nice -n 15 "$VENV_PY" \
    "$stage/memoria/scripts/mirror_external_episodes_to_bdr.py" \
    --source-sqlite "$SOURCE" \
    --checkpoint "$CHECKPOINT" \
    --output-directory "$output" \
    --bdr-library "$library" \
    --max-records 100000
sudo -u liveinfinita test -s "$output/report.json" || fail 'relatório de paridade ausente'
sudo -u liveinfinita "$VENV_PY" - "$output/report.json" <<'PY'
import json,sys
from pathlib import Path
r=json.loads(Path(sys.argv[1]).read_text())
assert r["schema"]=="memoria-v2-bdr-observed-episode-mirror-proof/v1",r
assert r["checkpoint_watermark_present"] is True,r
assert r["verified_cold_restart"] and r["verified_idempotent_replay"],r
assert r["source_snapshot_records"]==r["inserted_into_bdr"],r
assert not r["backend_cutover"] and not r["production_checkpoint_advanced"],r
assert not r["world_mutated"] and not r["central_sync"],r
print("MVP018D_CHECKPOINT_STABLE_DURING_COPY",r["checkpoint_unchanged_during_copy"])
print("MVP018D_BDR_SNAPSHOT_PARITY_OK",r["source_snapshot_records"],
      "bdr_sequence",r["bdr_durable_sequence"])
PY

for row in "$WORLD:$world_pid" "$CORE:$core_pid" "$RENDERER:$renderer_pid" "$API:$api_pid"; do
    IFS=: read -r unit expected <<< "$row"
    systemctl is-active --quiet "$unit" || fail "$unit não recuperou"
    [[ "$(systemctl show "$unit" -p MainPID --value)" == "$expected" ]] || fail "$unit reiniciou inesperadamente"
done
systemctl is-active --quiet "$TIMER" || fail 'timer de memória inativo'
"$VENV_PY" - <<'PY'
from urllib.request import urlopen
import json
with urlopen("http://127.0.0.1:8788/api/v1/storage/health", timeout=8) as reply:
    report=json.load(reply)
assert report["external_episode_persistence"]=="sqlite-incremental", report
print("MVP018D_OPERATIONAL_SQLITE_UNCHANGED records=",report["external_episode_observations"])
PY
echo "MVP018D_BDR_MIRROR_OK report=$output/report.json world_pid=$world_pid memory_pid=$core_pid"
echo 'MVP018D_BDR_MIRROR_FINISHED'
