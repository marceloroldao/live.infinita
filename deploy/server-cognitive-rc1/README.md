# Deploy — Server Cognitive RC1

Este diretório prepara o primeiro teste real do núcleo cognitivo sem TikTok, LLM ou Godot.

## 1. Branch

```bash
git fetch origin
git checkout release/server-cognitive-rc1
git pull --ff-only
```

## 2. Dependências fixadas

```bash
chmod +x deploy/server-cognitive-rc1/*.sh
./deploy/server-cognitive-rc1/bootstrap.sh
```

O script faz checkout exato de:

- Memoria.ia `45fdbe5b2404e00d40f492c2e503172a8eb22433`
- bit.analyze `2192c61e514a7bb500500ab9fff63bd42940dc52`

em `.vendor/`.

## 3. Smoke sem serviço

```bash
./deploy/server-cognitive-rc1/smoke.sh
```

Isso sobe temporariamente em `127.0.0.1:18090`, executa ciclos e encerra.

## 4. Execução manual

```bash
./deploy/server-cognitive-rc1/run.sh
```

Admin local:

```text
http://127.0.0.1:8090/
```

Para acessar remotamente sem abrir a porta pública:

```bash
ssh -L 8090:127.0.0.1:8090 USUARIO@SERVIDOR
```

e abra localmente:

```text
http://127.0.0.1:8090/
```

## 5. systemd user

```bash
mkdir -p ~/.config/systemd/user
cp deploy/server-cognitive-rc1/live-infinita-cognitive.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now live-infinita-cognitive.service
systemctl --user status live-infinita-cognitive.service
```

Logs:

```bash
journalctl --user -u live-infinita-cognitive.service -f
```

## Critério do primeiro teste

Antes de conectar qualquer entrada externa:

- `/health` permanece `ok`;
- `cycle_id` cresce sozinho;
- World tick/version crescem;
- Water ocupa/muda regiões;
- Nov produz ações `curiosity` ou `need`;
- pairwise links surgem;
- watermark avança monotonicamente;
- nenhuma rejeição tardia ocorre no fluxo interno ordenado;
- memória causal cresce;
- processo permanece estável por execução prolongada.

Restart/cold-reopen da cognição completa ainda não faz parte do RC1. Isso será adicionado depois que bit.analyze tiver snapshot/restore explícito dos associators.


## 6. Acompanhar o soak

Com o serviço em execução:

```bash
chmod +x deploy/server-cognitive-rc1/watch.sh
./deploy/server-cognitive-rc1/watch.sh
```

O watcher consulta `GET /soak` a cada 10 segundos. Para outro intervalo:

```bash
LIVE_COGNITIVE_WATCH_SECONDS=60 ./deploy/server-cognitive-rc1/watch.sh
```

Critérios durante o primeiro soak:

- `cycle_id`, world tick/version e `simulation_time` devem crescer;
- `max_event_time >= watermark`;
- `late_rejections = 0` no fluxo interno;
- `errors_in_activity_window = 0`;
- pairwise/causal memory devem aparecer sem explosão abrupta;
- o processo deve permanecer acessível por `/health`, `/snapshot` e `/soak`.
