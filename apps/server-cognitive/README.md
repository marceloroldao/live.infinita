# Server Cognitive RC1

Servidor operacional contínuo da Live Infinita construído sobre o freeze cognitivo do Life Gate 028.

## Autoridade

O serviço operacional é:

`apps/server-cognitive/server.py`

O World Runtime continua sendo a autoridade do mundo. O servidor cognitivo orquestra percepção, bit.analyze, Memoria.ia V2 e a vida autônoma da Nov. TikTok, LLM e renderer não participam deste RC1.

## Dependências congeladas

- Memoria.ia: `45fdbe5b2404e00d40f492c2e503172a8eb22433`
- bit.analyze: `2192c61e514a7bb500500ab9fff63bd42940dc52`
- base cognitiva Live Gate 028: `af2bbe43a28f472197c1bdebffc0413aa9d9d654`

## Execução

Depois de `deploy/server-cognitive-rc1/bootstrap.sh`:

```bash
./deploy/server-cognitive-rc1/run.sh
```

Bind padrão:

```text
127.0.0.1:8090
```

## Persistência

RC1 usa checkpoint JSON versionado e escrita atômica.

Estado persistido inclui:

- World State;
- necessidades da Nov;
- memória causal;
- regimes situados;
- memória temporal;
- memória higher-order;
- admission-state;
- TemporalAssociator;
- SparseContextAssociator;
- watermark/reorder buffer, inclusive slices pendentes;
- provenance;
- activity/rejections.

Variáveis:

```bash
LIVE_COGNITIVE_CHECKPOINT=var/server-cognitive-rc1/checkpoint.json
LIVE_COGNITIVE_AUTOSAVE_EVERY=10
LIVE_COGNITIVE_RESUME=1
```

O restart é considerado seguro somente se o checkpoint for carregado sem erro. O CI compara o próximo ciclo após restore com a mesma trajetória sem restart.

## Endpoints

- `GET /` — dashboard Admin mínimo.
- `GET /health` — saúde, autorun e estado do checkpoint.
- `GET /snapshot` — mundo, Nov, cognição, event-time e persistência.
- `GET /soak` — invariantes compactos.
- `GET /activity?limit=50` — atividade recente.
- `GET /debug/world` — World State completo.
- `GET /debug/memory` — memórias estruturais/causais.
- `POST /step` — um ciclo.
- `POST /run` — body `{"count": 10}`, limite 1000.
- `POST /checkpoint` — checkpoint imediato.
- `POST /flush` — flush explícito do event-time buffer.
- `POST /control` — autorun/intervalo.

## Ciclo

```text
World State
   ↓
frames multimodais
   ↓
Water/nature
   ↓
RealitySlice
   ↓
event-time reorder/watermark
   ↓
bit.analyze
   ↓
Memoria.ia temporal + higher-order + admission
   ↓
Nov curiosity/need
   ↓
World Runtime valida/comita
   ↓
memória causal
   ↓
autosave periódico
```

## Teste antes do servidor

`deploy/server-cognitive-rc1/smoke.sh` executa um smoke HTTP e também:

1. cria estado;
2. força checkpoint;
3. encerra o processo;
4. inicia novamente;
5. exige `loaded_from_checkpoint=true`;
6. exige o mesmo `cycle_id`;
7. continua a trajetória após o restart.

## Limites conscientes

RC1 ainda não recebe TikTok, LLM ou Godot. O primeiro teste real serve para observar vida contínua, crescimento das memórias, event-time, persistência e comportamento da Nov durante muitas horas.
