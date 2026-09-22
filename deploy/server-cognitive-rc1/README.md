# Deploy — Server Cognitive RC1

Primeiro teste real do núcleo cognitivo persistente, sem TikTok, LLM ou Godot.

## 1. Atualizar o repositório

Depois da primeira instalação, o caminho recomendado é:

```bash
cd ~/live.infinita
chmod +x deploy/update.sh
./deploy/update.sh
```

O script:

- aborta se houver alterações rastreadas locais;
- atualiza apenas por fast-forward;
- executa o bootstrap das dependências congeladas;
- reinicia o serviço se ele já estiver instalado.

## 2. Primeira instalação

```bash
cd ~/live.infinita
git fetch origin
git checkout release/server-cognitive-rc1
git pull --ff-only

chmod +x deploy/server-cognitive-rc1/*.sh deploy/update.sh
./deploy/server-cognitive-rc1/bootstrap.sh
./deploy/server-cognitive-rc1/smoke.sh
```

Dependências fixadas em `.vendor/`:

- Memoria.ia `45fdbe5b2404e00d40f492c2e503172a8eb22433`
- bit.analyze `2192c61e514a7bb500500ab9fff63bd42940dc52`

## 3. Checkpoint

Padrão:

```text
~/live.infinita/var/server-cognitive-rc1/checkpoint.json
```

O autosave padrão ocorre a cada 10 ciclos e o serviço tenta resume automaticamente.

O smoke valida restart real antes da instalação do systemd.

## 4. Instalar systemd user

```bash
./deploy/server-cognitive-rc1/install-service.sh
```

Depois:

```bash
systemctl --user status live-infinita-cognitive.service
journalctl --user -u live-infinita-cognitive.service -f
```

## 5. Admin

O serviço escuta somente:

```text
127.0.0.1:8090
```

Para acessar remotamente sem publicar a porta:

```bash
ssh -L 8090:127.0.0.1:8090 USUARIO@SERVIDOR
```

No navegador local:

```text
http://127.0.0.1:8090/
```

## 6. Acompanhar soak

```bash
./deploy/server-cognitive-rc1/watch.sh
```

Critérios:

- `cycle_id`, tick/version e simulation_time crescem;
- `max_event_time >= watermark`;
- fluxo interno mantém `late_rejections = 0`;
- `errors_in_activity_window = 0`;
- memórias causal/temporal/estrutural evoluem;
- checkpoint continua sendo atualizado;
- restart do serviço volta do cycle anterior, não de zero;
- endpoints permanecem responsivos.

## 7. Teste acelerado

```bash
curl -fsS -X POST \
  -H 'content-type: application/json' \
  -d '{"count":1000}' \
  http://127.0.0.1:8090/run

curl -fsS http://127.0.0.1:8090/soak
curl -fsS http://127.0.0.1:8090/health
```

Para checkpoint manual:

```bash
curl -fsS -X POST -H 'content-type: application/json' -d '{}' \
  http://127.0.0.1:8090/checkpoint
```

## 8. O que ainda fica desligado

- TikTok;
- LLM;
- Godot/renderer;
- entrada humana externa.

Essas camadas entram somente depois do soak cognitivo persistente.
