# Live Infinita

Narrativa interativa persistente em tempo real, impulsionada por IA e Memoria.ia.

A **Live Infinita** é um experimento de mundo persistente para transmissões ao vivo. O público participa por comentários e ações; um pipeline determinístico interpreta intenções, valida regras, atualiza o estado do mundo e usa uma LLM somente como operador probabilístico de interpretação/narrativa.

> Princípio central: **LLM, renderer e cliente nunca são a autoridade do mundo. O World State validado e versionado pela Memoria.ia é a fonte de verdade persistente.**

## Objetivos do MVP

- Capturar eventos de Live por adaptadores TikTok, YouTube e Simulator.
- Filtrar spam e agregar intenções antes de qualquer chamada generativa.
- Manter World State persistente com entidades, relações, eventos, claims, versões, deltas, snapshots, trajetórias e proveniência.
- Aplicar mudanças como deltas: `World(t+1) = World(t) + Delta(t)`.
- Usar regras determinísticas para validar ações antes do commit.
- Usar OpenAI inicialmente através de um `AI Router` substituível por modelos locais no futuro.
- Renderizar a cena via Web/Canvas/WebGL (PixiJS primeiro), sem depender de imagens pré-renderizadas como fonte de verdade.
- Integrar a saída ao OBS por Browser Source/WebSocket.
- Registrar métricas de latência, tokens, custo e erros de continuidade.

## Arquitetura

```text
TikTok / YouTube / Simulator
            |
            v
      Event Gateway
            |
            v
Filter / Vote / Guardrails
            |
            v
       Intent Engine
            |
            v
+-----------------------------+
| Memoria.ia / World State    |
| entities / relations        |
| events / claims / deltas    |
| versions / trajectories     |
+-------------+---------------+
              |
              v
      Deterministic Runtime
              |
        Proposed Action
              |
        validate / reject
              |
              v
          AI Router
       OpenAI -> local later
              |
              v
        Narrative Result
              |
        commit validated delta
              |
       +------+------+
       |             |
       v             v
      TTS      Web Scene Runtime
                     |
                  PixiJS
                     |
                  OBS
```

## Estrutura inicial

```text
live.infinita/
├─ apps/
│  ├─ gateway/             # ingestão TikTok/YouTube/Simulator
│  ├─ world-runtime/       # autoridade determinística do mundo
│  ├─ ai-router/           # OpenAI hoje, modelos locais depois
│  └─ renderer-web/        # PixiJS/WebGL + Browser Source OBS
├─ packages/
│  ├─ world-model/         # tipos e operações do World State
│  ├─ contracts/           # schemas JSON entre serviços
│  └─ observability/       # tick_id, latência, tokens, custo, CER
├─ schemas/
│  ├─ world-state.schema.json
│  ├─ entity.schema.json
│  ├─ relation.schema.json
│  ├─ event.schema.json
│  ├─ delta.schema.json
│  └─ proposed-action.schema.json
├─ examples/
│  └─ world-state.minimal.json
├─ docs/
│  ├─ ARCHITECTURE.md
│  └─ WORLD_STATE.md
└─ tests/
```

## Princípios

1. **Estado antes de narrativa** — narrativa nunca substitui o estado estruturado.
2. **Delta, não regeneração** — mudanças acrescentam ou alteram partes do mundo sem destruir o restante.
3. **Identidade persistente** — cada entidade possui ID estável e trajetória.
4. **Proveniência obrigatória** — toda mudança relevante deve saber de onde veio.
5. **Claims não são fatos** — afirmações podem coexistir em conflito até serem reforçadas ou resolvidas.
6. **LLM propõe; Runtime valida; Memoria.ia persiste.**
7. **Renderer é projeção** — PixiJS/Three.js/HTML/WebGL representam o World State, mas não o definem.
8. **Contexto limitado** — o tamanho do mundo não deve crescer proporcionalmente ao prompt da LLM.
9. **Replay determinístico** — eventos e deltas devem permitir reproduzir uma sessão e comparar versões da Memoria.ia.
10. **Idle sem custo generativo** — sem interação, o mundo pode continuar animado sem chamadas à LLM.

## Estado do projeto

**Fase:** arquitetura / MVP inicial.

Próximo marco: executar um mundo mínimo local com Simulator -> Intent -> World Runtime -> Delta -> Renderer Web, sem depender de uma Live real.
