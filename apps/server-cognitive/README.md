# Server Cognitive RC1

Primeiro perfil de servidor contínuo da Live Infinita depois do congelamento cognitivo do Life Gate 028.

## Objetivo

Rodar por tempo prolongado, sem TikTok, sem LLM e sem renderer obrigatório:

- World Runtime como autoridade;
- Nov com curiosity + necessidades locais;
- Water distribuída evoluindo pelo runtime físico;
- percepção multimodal;
- RealitySlices;
- bit.analyze pairwise + higher-order;
- Memoria.ia V2 histórica + admission-state;
- event-time/watermark;
- observabilidade HTTP/Admin.

## Dependências fixadas

- Memoria.ia: `45fdbe5b2404e00d40f492c2e503172a8eb22433`
- bit.analyze: `2192c61e514a7bb500500ab9fff63bd42940dc52`
- Live cognitive freeze: `af2bbe43a28f472197c1bdebffc0413aa9d9d654`

O bootstrap padrão espera:

```text
live.infinita/
├─ .vendor/
│  ├─ memoria.ia/
│  └─ bit.analyze/
├─ apps/
│  ├─ world-runtime/
│  └─ server-cognitive/
```

## Execução

Depois do bootstrap das dependências:

```bash
python3 apps/server-cognitive/server.py
```

Por segurança, o bind padrão é:

```text
127.0.0.1:8090
```

Variáveis:

```bash
LIVE_COGNITIVE_HOST=127.0.0.1
LIVE_COGNITIVE_PORT=8090
LIVE_COGNITIVE_AUTORUN=1
LIVE_COGNITIVE_STEP_SECONDS=1.0
```

## Endpoints

- `GET /` — Admin Web mínimo.
- `GET /health` — saúde/autorun.
- `GET /snapshot` — estado resumido de mundo, Nov, cognition e watermark.
- `GET /activity?limit=50` — ciclos recentes.
- `GET /debug/world` — World State completo.
- `GET /debug/memory` — snapshots das memórias estruturais/causais.
- `POST /step` — um ciclo.
- `POST /run` — vários ciclos, body `{"count": 10}`, limite 1000.
- `POST /flush` — flush explícito do buffer event-time.
- `POST /control` — `{"autorun": true|false, "interval_seconds": 1.0}`.

## Um ciclo do RC1

```text
World State
   ↓
3 frames multimodais
   ↓
Water avança entre frames
   ↓
RealitySlice
   ↓
event-time reorder/watermark
   ↓
TemporalAssociator + SparseContextAssociator
   ↓
Memoria.ia structural observation/admission
   ↓
Nov escolhe por curiosity ou necessidade
   ↓
World Runtime valida e comita
   ↓
consequência real
   ↓
SituatedLiveCognitiveGymV2 aprende
```

## Limite consciente do RC1

O RC1 já expõe snapshots duráveis das memórias da Memoria.ia, mas **ainda não declara restart cognitivo completo**. Os associators do bit.analyze não possuem neste freeze um contrato público de snapshot/restore equivalente.

Não será usado pickle opaco para mascarar essa lacuna.

A sequência de servidor prevista é:

1. provar vida contínua por muitas horas;
2. medir crescimento/memória/latência;
3. adicionar checkpoint estrutural reproduzível para bit.analyze;
4. provar restart/cold reopen;
5. liberar entrada humana via simulator/chat;
6. só então reconectar TikTok, Godot e LLM opcional.
