# Live Infinita

Narrativa interativa persistente em tempo real, impulsionada por IA e Memoria.ia.

A **Live Infinita** é um experimento de mundo persistente para transmissões ao vivo. O público participa por comentários e ações; um pipeline determinístico interpreta intenções, valida regras, atualiza o estado do mundo e usa uma LLM somente como operador probabilístico de interpretação/narrativa.

> Princípio central: **LLM, renderer e cliente nunca são a autoridade do mundo. O World State validado pelo Runtime e persistido pela Memoria.ia é a fonte de verdade persistente.**

## Requisitos obrigatórios do MVP

- Capturar eventos por adaptadores TikTok, YouTube e Simulator.
- Filtrar spam e agregar intenções antes de qualquer chamada generativa.
- Manter World State persistente com entidades, relações, eventos, claims, versões, deltas, snapshots, trajetórias e proveniência.
- Aplicar mudanças como deltas: `World(t+1) = World(t) + Delta(t)`.
- Usar regras determinísticas para validar ações antes do commit.
- A LLM nunca escreve diretamente no World State; ela somente interpreta e propõe.
- A Memoria.ia deve ser acessada por um contrato `WorldStore`/adapter, sem acoplamento direto do Runtime ao backend de persistência.
- O MVP não pode ficar bloqueado por uma refatoração da Memoria.ia: deve existir um `LocalWorldStore` inicial e um `MemoriaIaWorldStore` intercambiável.
- O renderer principal do mundo é **Godot 4**, usando GDScript, 2D/2.5D inicialmente, geração procedural, partículas, animações e shaders quando necessário.
- O antigo `renderer-web/PixiJS` não é mais o renderer principal; tecnologias web ficam reservadas para painel administrativo, observabilidade e preview.
- A narração inicial usa **uma única voz de narrador**, sem vozes individuais por personagem.
- O TTS inicial deve ser **local e de baixo custo**, com Piper como baseline. TTS em nuvem deve permanecer opcional e substituível.
- Sem interação do público, o mundo entra em modo idle: animações visuais continuam localmente, mas não há chamadas obrigatórias de LLM nem criação artificial de deltas.
- Deve existir **Admin Web** acessível remotamente com World State, eventos, deltas, métricas, status do renderer, status do TTS e preview do mundo.
- O servidor Linux não deve exigir GNOME/KDE para o backend. Componentes gráficos devem ser desacoplados e podem usar renderização nativa/offscreen conforme evolução do projeto.
- A saída inicial para Live pode ser Godot nativo -> OBS. Evoluções futuras podem usar Spout/NDI/FFmpeg/GStreamer/RTMP/SRT sem alterar o World State.
- Registrar métricas de latência, tokens, custo, ações aceitas/rejeitadas e erros de continuidade.

## Arquitetura-alvo

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
      Proposed Action
            |
            v
   Deterministic Runtime
       validate / reject
            |
            v
        World Delta
            |
      +-----+-------------------+
      |                         |
      v                         v
  WorldStore                Event Stream
      |                         |
      |                    +----+-----+
      |                    |          |
      v                    v          v
LocalWorldStore       renderer-godot  narration
ou MemoriaIaWorldStore     |          |
                           |       Piper local
                           v          |
                       cena visual    |
                           |          |
                           +----+-----+
                                v
                              OBS

Admin Web <---- métricas / estado / preview ---- Runtime + Renderer
```

## Estrutura planejada

```text
live.infinita/
├─ apps/
│  ├─ gateway/              # Python: TikTok/YouTube/Simulator
│  ├─ world-runtime/        # Python: autoridade determinística
│  ├─ ai-router/            # Python: OpenAI inicialmente, local depois
│  ├─ narration/            # Python: templates + Piper local
│  ├─ renderer-godot/       # Godot 4 / GDScript
│  └─ admin-web/            # HTML/CSS/JS: painel e preview
├─ packages/
│  ├─ world-model/          # tipos e operações do World State
│  ├─ contracts/            # contratos entre serviços
│  ├─ world-store/          # LocalWorldStore + MemoriaIaWorldStore
│  └─ observability/        # tick_id, latência, tokens, custo, CER
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
│  ├─ WORLD_STATE.md
│  └─ REQUIREMENTS.md
└─ tests/
```

## Princípios

1. **Estado antes de narrativa** — narrativa nunca substitui o estado estruturado.
2. **Delta, não regeneração** — mudanças acrescentam ou alteram partes do mundo sem destruir o restante.
3. **Identidade persistente** — cada entidade possui ID estável e trajetória.
4. **Proveniência obrigatória** — toda mudança relevante deve saber de onde veio.
5. **Claims não são fatos** — afirmações podem coexistir em conflito até serem reforçadas ou resolvidas.
6. **LLM propõe; Runtime valida; WorldStore persiste.**
7. **Renderer é projeção** — Godot representa o World State, mas não o define.
8. **Contexto limitado** — o tamanho do mundo não deve crescer proporcionalmente ao prompt da LLM.
9. **Replay determinístico** — eventos e deltas devem permitir reproduzir uma sessão e comparar versões da Memoria.ia.
10. **Idle sem custo generativo** — sem interação, o mundo pode continuar visualmente vivo sem uso obrigatório de LLM.
11. **Baixo custo primeiro** — nenhuma dependência paga deve ser obrigatória no MVP-001.
12. **Infraestrutura substituível** — renderer, TTS, LLM e persistência são adapters; o domínio não depende de uma implementação específica.

## Estado do projeto

**Fase:** arquitetura / MVP inicial.

Próximo marco: executar um mundo mínimo local com `Simulator -> Intent -> ProposedAction -> Runtime -> Delta -> LocalWorldStore -> Godot`, com narração local por Piper, modo idle e Admin Web com preview. Depois conectar `MemoriaIaWorldStore` sem alterar o Runtime.
