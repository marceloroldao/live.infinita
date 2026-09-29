#!/usr/bin/env bash
# Isolated installation: real pinned Memoria.ia V2, local to this VM.
# Never installs into or restarts Nov, Godot, Live API, or central Memoria.ia.
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
CORE_SHA=3ea447c449349761215c43182ca54a0941b6e09b
REQUIRED=cae61891e64364978ba125f3137fa1ce164376bb
CORE_ROOT=/opt/live-infinita-memoria-core
CORE_DIR="$CORE_ROOT/$CORE_SHA"
DATA_DIR=/var/lib/live-infinita/memoria-local
ENV_FILE=/etc/live-infinita/memoria-local.env
CORE_UNIT=live-infinita-memoria-local.service
WORKER_UNIT=live-infinita-memoria-nov-sync.service
TIMER_UNIT=live-infinita-memoria-nov-sync.timer
WORLD_UNIT=live-infinita-autonomous-world.service
LIVE_API=live-infinita.service
RENDERER=live-infinita-renderer.service
AUDIO=live-infinita-audio.service
RELAY=live-infinita-audio-web.service
WORKER=apps/world-runtime/nov_local_memory_sync.py
fail(){ echo "MVP018C_LOCAL_MEMORIA_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail 'Execute como etbra: bash deploy/mvp018c-memoria-local.sh'
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail 'Checkout fora da main'
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail 'Checkout com modificações rastreadas'
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail 'Atualize o checkout main antes de instalar'
git merge-base --is-ancestor "$REQUIRED" HEAD || fail 'MVP-018C ainda não integrado à main'
for svc in "$WORLD_UNIT" "$LIVE_API" "$RENDERER" "$AUDIO" "$RELAY"; do
    systemctl is-active --quiet "$svc" || fail "$svc inativo"
done
[[ ! -e "/etc/systemd/system/$CORE_UNIT" && ! -e "/etc/systemd/system/$WORKER_UNIT" &&
   ! -e "/etc/systemd/system/$TIMER_UNIT" ]] || fail 'Instância local já instalada: não sobrescrever automaticamente'
if systemctl is-active --quiet live-infinita-broadcaster.service; then
    fail 'Não instalar durante uma transmissão ativa'
fi
world_pid="$(systemctl show "$WORLD_UNIT" -p MainPID --value)"
api_pid="$(systemctl show "$LIVE_API" -p MainPID --value)"
renderer_pid="$(systemctl show "$RENDERER" -p MainPID --value)"
audio_pid="$(systemctl show "$AUDIO" -p MainPID --value)"
relay_pid="$(systemctl show "$RELAY" -p MainPID --value)"
echo "BEFORE world=$world_pid api=$api_pid renderer=$renderer_pid audio=$audio_pid relay=$relay_pid"

bash -n "$REPO/deploy/mvp018c-memoria-local.sh"
PYTHONPATH=.:apps/world-runtime:apps/audio-service:apps/audience "$INSTALL/.venv/bin/python" -m unittest \
    tests.test_nov_local_memory_sync tests.test_nov_episode_sync_preview tests.test_nov_life_observability

# Fetch the actual V2 core by immutable commit; never take whatever is newest.
stage="$(mktemp -d /tmp/live-memoria-v2.XXXXXXXX)"
applied=0
rollback(){
    if (( applied )); then
        echo 'MVP018C_LOCAL_MEMORIA_ROLLBACK: removendo apenas novos serviços, preservando dados locais' >&2
        sudo systemctl disable --now "$TIMER_UNIT" 2>/dev/null || true
        sudo systemctl stop "$WORKER_UNIT" "$CORE_UNIT" 2>/dev/null || true
        sudo rm -f "/etc/systemd/system/$CORE_UNIT" "/etc/systemd/system/$WORKER_UNIT" "/etc/systemd/system/$TIMER_UNIT"
        if (( worker_preexisted )); then
            sudo cp -a "$stage/previous-worker.py" "$INSTALL/$WORKER"
        else
            sudo rm -f "$INSTALL/$WORKER"
        fi
        sudo systemctl daemon-reload || true
        # Never delete DATA_DIR, the API key, or snapshots from a partial ingest.
    fi
    rm -rf -- "$stage"
}
trap rollback EXIT

git clone -q --filter=blob:none --depth 1 https://github.com/marceloroldao/memoria.ia.git "$stage/core"
git -C "$stage/core" fetch -q --depth 1 origin "$CORE_SHA"
git -C "$stage/core" checkout -q --detach "$CORE_SHA"
[[ "$(git -C "$stage/core" rev-parse HEAD)" == "$CORE_SHA" ]] || fail 'Memoria.ia core commit divergiu'
[[ -f "$stage/core/src/memoria_resolutiva/product_server.py" &&
   -f "$stage/core/src/memoria_resolutiva/external_episode_contract.py" ]] ||
    fail 'Core V2 ou contrato episódico ausente'

# Prove real V2 persistence, authentication and idempotent ACK before sudo.
mkdir -m 0700 "$stage/test-data"
PYTHONPATH="$stage/core/src:$REPO" \
MEMORIA_ORGANIZATION_ID=live-infinita-local \
MEMORIA_NODE_ID=live-infinita-local:nov \
MEMORIA_API_KEY=local-test-key-0123456789abcdefghijklmnopqrstuvwxyz \
MEMORIA_DATA_DIR="$stage/test-data" \
MEMORIA_STORAGE_BACKEND=sqlite \
MEMORIA_STORAGE_ALLOW_FALLBACK=false \
MEMORIA_CONVERSATION_RUNTIME=python \
MEMORIA_EPISODIC_RUNTIME=python \
"$INSTALL/.venv/bin/python" - <<'PY'
import os
from fastapi.testclient import TestClient
from memoria_resolutiva.product_server import app
from packages.observability.nov_episode_sync import observation_envelope
row = {
    "episode_schema":"npc_episode_v1", "episode_id":"plan:local-preflight",
    "npc_id":"nov", "logical_tick":7, "need":"curiosity",
    "target_entity_id":"ancient_tree", "strategy_id":"explore",
    "context":{}, "outcome":{"satisfaction":0.5},
    "source":{"kind":"need_outcome","plan_id":"local-preflight",
              "proposal_id":"local-preflight","plan_revision":0},
}
envelope = observation_envelope(row, world_id="nov-live-autonomous-001")
with TestClient(app) as client:
    health = client.get("/api/v1/storage/health")
    assert health.status_code == 200, health.text
    status = health.json()
    assert status["conversation_runtime"] == "python"
    assert status["episodic_runtime"] == "python"
    assert status["backend"] == "sqlite"
    assert client.post("/api/v1/external/episodes",json=envelope).status_code == 401
    key = {"X-Memoria-Key":"local-test-key-0123456789abcdefghijklmnopqrstuvwxyz"}
    first = client.post("/api/v1/external/episodes",json=envelope,headers=key)
    again = client.post("/api/v1/external/episodes",json=envelope,headers=key)
    assert first.status_code == 201 and again.status_code == 201,(first.text,again.text)
    assert first.json()["ack"] is True and first.json()["stored"] is True
    assert again.json()["ack"] is True and again.json()["stored"] is False
    assert first.json()["content_sha256"] == envelope["content_sha256"]
    assert first.json()["persistence"]["backend"] == "sqlite"
    assert first.json()["persistence"]["state_id"]
    # Real disk-growth gate: this pin persists a full EvidenceCore snapshot per
    # episode. Do not enable an unbounded timer until the backend is incremental.
    from pathlib import Path
    for i in range(1, 8):
        sample = {
            **row,
            "episode_id": f"plan:local-preflight-{i}",
            "logical_tick": 7 + i,
            "source": {
                **row["source"], "plan_id": f"local-preflight-{i}",
                "proposal_id": f"local-preflight-{i}",
            },
        }
        item = observation_envelope(sample, world_id="nov-live-autonomous-001")
        response = client.post("/api/v1/external/episodes", json=item, headers=key)
        assert response.status_code == 201 and response.json()["ack"] is True, response.text
    disk_bytes = sum(p.stat().st_size for p in Path(os.environ["MEMORIA_DATA_DIR"]).rglob("*") if p.is_file())
    print("MVP018C_LOCAL_MEMORIA_DISK_GATE", "episodes=8", f"bytes={disk_bytes}", flush=True)
    if disk_bytes > 8 * 1024 * 1024:
        raise SystemExit("MVP018C_LOCAL_MEMORIA_DISK_GATE_FAIL: snapshot storage exceeds 8 MiB for 8 episodes; refusing production timer")
print("MVP018C_LOCAL_CORE_PREFLIGHT_OK")
PY

sudo -v
# Dedicated owner-only data; no shared database with the World State.
sudo install -d -o liveinfinita -g liveinfinita -m 0700 "$DATA_DIR"
sudo install -d -o root -g root -m 0755 "$CORE_ROOT" "$CORE_DIR" "$CORE_DIR/src"
sudo cp -a "$stage/core/src/memoria_resolutiva" "$CORE_DIR/src/"
echo "$CORE_SHA" | sudo tee "$CORE_DIR/commit.sha" > /dev/null
sudo chown -R root:root "$CORE_DIR"
sudo chmod -R go-w "$CORE_DIR"

# Generate an independent key without printing it or sharing the Live token.
sudo /usr/bin/python3 - "$ENV_FILE" <<'PY'
import os, secrets, sys
from pathlib import Path
path = Path(sys.argv[1])
if path.is_symlink():
    raise SystemExit("memoria-local env is a symlink")
if path.exists():
    if path.stat().st_mode & 0o077:
        raise SystemExit("existing memoria-local env is not private")
    contents = path.read_text()
    if "MEMORIA_ORGANIZATION_ID=live-infinita-local\n" not in contents or "MEMORIA_API_KEY=" not in contents:
        raise SystemExit("existing memoria-local env does not match expected identity")
else:
    contents = "\n".join((
        "MEMORIA_ORGANIZATION_ID=live-infinita-local",
        "MEMORIA_ORGANIZATION_NAME=Live Infinita Local",
        "MEMORIA_NODE_ID=live-infinita-local:nov",
        "MEMORIA_API_KEY=" + secrets.token_hex(32),
        "MEMORIA_DATA_DIR=/var/lib/live-infinita/memoria-local",
        "MEMORIA_STORAGE_BACKEND=sqlite",
        "MEMORIA_STORAGE_ALLOW_FALLBACK=false",
        "MEMORIA_CONVERSATION_RUNTIME=python",
        "MEMORIA_EPISODIC_RUNTIME=python",
        "MEMORIA_CONCEPT_NAMESPACE=live-local",
    )) + "\n"
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(contents)
        f.flush()
        os.fsync(f.fileno())
PY

worker_preexisted=0
if [[ -e "$INSTALL/$WORKER" ]]; then
    worker_preexisted=1
    sudo cp -a "$INSTALL/$WORKER" "$stage/previous-worker.py"
fi
applied=1
sudo install -o liveinfinita -g liveinfinita -m 0644 "$REPO/$WORKER" "$INSTALL/$WORKER"
for unit in "$CORE_UNIT" "$WORKER_UNIT" "$TIMER_UNIT"; do
    sudo install -o root -g root -m 0644 "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
    cmp "$REPO/deploy/$unit" "/etc/systemd/system/$unit"
done
cmp "$REPO/$WORKER" "$INSTALL/$WORKER"
sudo "$INSTALL/.venv/bin/python" -m py_compile "$INSTALL/$WORKER"
sudo systemctl daemon-reload
sudo systemctl enable --now "$CORE_UNIT"
ready=0
for attempt in $(seq 1 30); do
    if systemctl is-active --quiet "$CORE_UNIT" &&
       curl -fsS --max-time 5 -o /dev/null http://127.0.0.1:8788/api/v1/health 2>/dev/null; then
        ready=1; break
    fi
    sleep 2
done
(( ready )) || fail 'Core local não iniciou'

# Typed ingress must be authenticated. No production test fixture is written.
[[ "$(curl -sS --max-time 6 -o /dev/null -w '%{http_code}' -H 'Content-Type: application/json' \
    --data '{}' http://127.0.0.1:8788/api/v1/external/episodes)" == 401 ]] ||
    fail 'Ingress local não exige chave'
curl -fsS --max-time 8 http://127.0.0.1:8788/api/v1/storage/health |
    "$INSTALL/.venv/bin/python" -c \
    'import json,sys; d=json.load(sys.stdin); assert d["backend"]=="sqlite"; assert d["conversation_runtime"]=="python" and d["episodic_runtime"]=="python"; print("MVP018C_LOCAL_HEALTH_OK")'

# Ingest at most two *real* episodes, strictly in the separate local store.
sudo systemctl start "$WORKER_UNIT"
systemctl show "$WORKER_UNIT" -p Result --value | grep -Fx success >/dev/null ||
    fail 'Primeira ingestão local não terminou com sucesso'
journalctl -u "$WORKER_UNIT" --since '5 minutes ago' --no-pager |
    grep -F 'LOCAL_MEMORIA_SYNC_OK' >/dev/null ||
    fail 'Nenhum recibo de ingestão local confirmado'
[[ -s "$DATA_DIR/nov-ingest.checkpoint.json" && -s "$DATA_DIR/evidence/receipt.json" ]] ||
    fail 'Checkpoint local ou recibo V2 não foi persistido'

# Low-rate timer. No Live API, renderer or Single Writer dependency.
sudo systemctl enable --now "$TIMER_UNIT"
systemctl is-active --quiet "$TIMER_UNIT" || fail 'Timer local indisponível'
for row in "$WORLD_UNIT:$world_pid" "$LIVE_API:$api_pid" "$RENDERER:$renderer_pid" "$AUDIO:$audio_pid" "$RELAY:$relay_pid"; do
    IFS=: read -r svc expected <<<"$row"
    systemctl is-active --quiet "$svc" || fail "$svc ficou inativo"
    [[ "$(systemctl show "$svc" -p MainPID --value)" == "$expected" ]] ||
        fail "$svc teve reinício inesperado"
done
applied=0
echo "MVP018C_LOCAL_MEMORIA_DEPLOY_OK world_pid=$world_pid core_pid=$(systemctl show "$CORE_UNIT" -p MainPID --value)"
echo "LOCAL_MEMORIA_DATA=$DATA_DIR"
echo "LOCAL_MEMORIA_ROUTE=127.0.0.1:8788"
echo "CENTRAL_SYNC=false"
echo "MVP018C_LOCAL_MEMORIA_FINISHED"
