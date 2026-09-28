#!/usr/bin/env bash
set -Eeuo pipefail

REPO=/home/etbra/live.infinita
INSTALL=/opt/live.infinita
WORLD=live-infinita-autonomous-world.service
API=live-infinita.service
AUDIO=live-infinita-audio.service
REQUIRED=53a4b001767d0b59d6649627fce7096ee8b93b07
fail(){ echo "NARRATOR_DEPLOY_FAIL: $*" >&2; exit 2; }
(( EUID != 0 )) || fail "Execute como etbra: bash deploy/narrator-ws-hotfix.sh"
cd "$REPO"
[[ "$(git branch --show-current)" == main ]] || fail "Checkout fora da main"
[[ -z "$(git status --porcelain --untracked-files=no)" ]] || fail "Alterações rastreadas locais"
git fetch origin main
[[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]] || fail "Atualize o checkout antes do deploy"
git merge-base --is-ancestor "$REQUIRED" HEAD || fail "Correção de importação do narrador não integrada"
systemctl is-active --quiet "$WORLD" || fail "Single Writer inativo"
world_pid="$(systemctl show "$WORLD" -p MainPID --value)"
[[ "$world_pid" =~ ^[0-9]+$ && "$world_pid" -gt 1 ]] || fail "PID autoritativo inválido"
echo "== Testes focalizados =="
PYTHONPATH=.:apps/world-runtime:apps/audio-service:apps/audience \
  "$INSTALL/.venv/bin/python" -m unittest \
  tests.test_narration_spool tests.test_live_presentation_narration tests.test_manager_live_simulator \
  tests.test_story_narrator tests.test_retro_world_audio \
  tests.test_spatial_session tests.test_spatial_multi_observer
sudo -v
backup="/var/backups/live-infinita/narrator-ws-$(date +%Y%m%d-%H%M%S)"
sudo install -d -m 0700 "$backup"
sudo cp -a "$INSTALL/apps/audio-service/retro_audio.py" "$backup/retro_audio.py"
sudo cp -a "$INSTALL/apps/world-runtime/main_spatial.py" "$backup/main_spatial.py"
sudo cp -a "$INSTALL/apps/world-runtime/main_live.py" "$backup/main_live.py"
if [[ -f "$INSTALL/packages/narration_spool.py" ]]; then
  sudo cp -a "$INSTALL/packages/narration_spool.py" "$backup/narration_spool.py"
fi
echo "BACKUP=$backup"
applied=0
rollback(){
  if (( applied )); then
    echo "ROLLBACK: restaurando os arquivos de apresentação do narrador" >&2
    sudo cp -a "$backup/retro_audio.py" "$INSTALL/apps/audio-service/retro_audio.py"
    sudo cp -a "$backup/main_spatial.py" "$INSTALL/apps/world-runtime/main_spatial.py"
    sudo cp -a "$backup/main_live.py" "$INSTALL/apps/world-runtime/main_live.py"
    if [[ -f "$backup/narration_spool.py" ]]; then
      sudo cp -a "$backup/narration_spool.py" "$INSTALL/packages/narration_spool.py"
    else
      sudo rm -f "$INSTALL/packages/narration_spool.py"
    fi
    sudo systemctl restart "$API" "$AUDIO" || true
  fi
}
trap rollback EXIT
applied=1
sudo install -o liveinfinita -g liveinfinita -m 0644 \
  "$REPO/apps/audio-service/retro_audio.py" "$INSTALL/apps/audio-service/retro_audio.py"
sudo install -o liveinfinita -g liveinfinita -m 0644 \
  "$REPO/apps/world-runtime/main_spatial.py" "$INSTALL/apps/world-runtime/main_spatial.py"
sudo install -o liveinfinita -g liveinfinita -m 0644 \
  "$REPO/apps/world-runtime/main_live.py" "$INSTALL/apps/world-runtime/main_live.py"
sudo install -o liveinfinita -g liveinfinita -m 0644 \
  "$REPO/packages/narration_spool.py" "$INSTALL/packages/narration_spool.py"
cmp "$REPO/apps/audio-service/retro_audio.py" "$INSTALL/apps/audio-service/retro_audio.py"
cmp "$REPO/apps/world-runtime/main_spatial.py" "$INSTALL/apps/world-runtime/main_spatial.py"
cmp "$REPO/apps/world-runtime/main_live.py" "$INSTALL/apps/world-runtime/main_live.py"
cmp "$REPO/packages/narration_spool.py" "$INSTALL/packages/narration_spool.py"
sudo "$INSTALL/.venv/bin/python" -m py_compile \
  "$INSTALL/apps/audio-service/retro_audio.py" "$INSTALL/apps/world-runtime/main_spatial.py" \
  "$INSTALL/apps/world-runtime/main_live.py" "$INSTALL/packages/narration_spool.py"
# Verify the real production import layout, not only py_compile.
sudo -u liveinfinita "$INSTALL/.venv/bin/python" -c \
  "import sys; sys.path.insert(0, \"$INSTALL/apps/audio-service\"); import retro_audio; from packages.narration_spool import read_cues; print(\"NARRATOR_PRODUCTION_IMPORT_OK\")"
sudo systemctl restart "$API" "$AUDIO"
ready=0
for attempt in $(seq 1 12); do
  if curl -fsS --max-time 8 http://127.0.0.1:8080/api/health |
    python3 -c 'import json,sys;assert json.load(sys.stdin)["ok"] is True'; then
    ready=1; break
  fi
  sleep 2
done
(( ready == 1 )) || fail "Health da API indisponível"
systemctl is-active --quiet "$AUDIO" || fail "Serviço de áudio inativo"
systemctl is-active --quiet "$WORLD" || fail "Single Writer inativo após deploy"
[[ "$(systemctl show "$WORLD" -p MainPID --value)" == "$world_pid" ]] ||
  fail "Single Writer reiniciou inesperadamente"
trap - EXIT
applied=0
echo "NARRATOR_DEPLOY_OK: API e áudio reiniciados; Single Writer preservado"
echo "== Teste ponta a ponta (bloqueado automaticamente durante TikTok LIVE) =="
sudo "$INSTALL/.venv/bin/python" - <<'PY'
import json, pathlib, time, urllib.request
root=pathlib.Path("/var/lib/live-infinita/audio")
env=pathlib.Path("/etc/live-infinita/operator.env").read_text()
token=next((line.partition("=")[2].strip() for line in env.splitlines()
            if line.startswith("LIVE_INFINITA_OPERATOR_TOKEN=")), "")
assert token, "Chave de operador indisponível"
base="http://127.0.0.1:8080"
def request(path, payload=None):
    data=None if payload is None else json.dumps(payload).encode()
    headers={"Authorization":"Bearer "+token}
    if data is not None: headers["Content-Type"]="application/json"
    with urllib.request.urlopen(urllib.request.Request(base+path, data=data, headers=headers),
                                timeout=65) as response:
        return json.load(response)
state=request("/api/manage/simulator/state")
if state.get("live_active"):
    print("NARRATOR_E2E_SKIPPED: TikTok LIVE ativa; não injetar visitante de teste")
    raise SystemExit(0)
events=root/"narration-events.jsonl"
offset=events.stat().st_size if events.exists() else 0
metrics=root/"native-metrics.txt"
def voice_chunks():
    try:
        return int(next(line.partition("=")[2] for line in metrics.read_text().splitlines()
                        if line.startswith("voice_chunks=")))
    except (OSError, StopIteration, ValueError):
        return None
before=voice_chunks()
reply=request("/api/manage/simulator/comment", {
    "actor_id":"narrator-diagnostic",
    "display_name":"Diagnóstico",
    "text":"Olá! Esta é uma verificação técnica do narrador.",
    "allow_during_live":False,
})
cue=reply.get("narration_cue") or {}
identity=cue.get("cue_id")
if not identity or not cue.get("text"):
    print("NARRATOR_E2E_NO_CUE:",reply.get("narration_suppressed") or "sem resposta")
    raise SystemExit(3)
print("NARRATOR_CUE_OK:",identity)
for _ in range(50):
    time.sleep(1)
    try:
        with events.open(encoding="utf-8") as f:
            f.seek(offset)
            rows=[json.loads(line) for line in f if line.strip()]
    except (OSError,ValueError,json.JSONDecodeError):
        rows=[]
    matched=next((r for r in rows if r.get("event_identity")==identity),None)
    if not matched:
        continue
    print("TTS_EVENT:",matched.get("provider"),"ok=",matched.get("ok"),
          "pcm_bytes=",matched.get("queued_pcm_bytes",0))
    if not matched.get("ok") or not matched.get("queued_pcm_bytes"):
        raise SystemExit(4)
    if before is not None:
        for _ in range(15):
            after=voice_chunks()
            if after is not None and after>before:
                print("NARRATOR_E2E_OK: voice_chunks",before,"->",after)
                raise SystemExit(0)
            time.sleep(1)
        print("NARRATOR_E2E_PCM_OK: PCM entregue; mixer não confirmou incremento")
        raise SystemExit(5)
    print("NARRATOR_E2E_PCM_OK: PCM entregue; métricas nativas indisponíveis")
    raise SystemExit(0)
print("NARRATOR_E2E_TIMEOUT: cue sem evento TTS correspondente")
raise SystemExit(6)
PY
