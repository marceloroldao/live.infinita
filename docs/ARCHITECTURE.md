# Arquitetura — Live Infinita

## Regra de autoridade

A única autoridade persistente é o **World Runtime + Memoria.ia**.

- Chat propõe intenções.
- LLM interpreta e narra.
- Runtime valida.
- Memoria.ia persiste o estado aceito.
- Renderer apenas projeta o estado.

## Fluxo crítico

```text
Live Adapter -> Event Gateway -> Filter/Aggregator -> Intent
-> Context Compiler -> AI Router -> Proposed Action
-> World Runtime -> Delta -> Memoria.ia -> Renderer/TTS/OBS
```

## Serviços

### gateway
Normaliza eventos externos em `LiveEvent` e suporta TikTok, YouTube e Simulator.

### world-runtime
Mantém o estado autoritativo, aplica regras, valida `ProposedAction`, gera `Delta`, eventos e versões.

### ai-router
Abstrai provedores de inferência. V0.x usa OpenAI. A interface deve permitir substituição por llama.cpp/vLLM sem alterar o domínio.

### renderer-web
Recebe apenas projeções do estado e deltas visuais. PixiJS é o renderer inicial; Three.js pode entrar depois para regiões 3D.

## Loop narrativo

1. Eventos chegam continuamente.
2. Uma janela/tick agrega mensagens.
3. Filtros determinísticos removem ruído.
4. A intenção coletiva é estruturada.
5. Memoria.ia fornece apenas o contexto relevante.
6. A LLM retorna narrativa + ações propostas em schema rígido.
7. O Runtime valida cada ação.
8. Ações aceitas geram deltas versionados.
9. Memoria.ia persiste o novo estado.
10. Renderer e TTS recebem somente a saída necessária.

## Idle

Sem interação do público, não há necessidade de chamar a LLM. O renderer mantém animações locais (partículas, iluminação, respiração, clima) a partir do Scene State atual.

## Métricas mínimas

Cada tick deve registrar:

- `tick_id`
- eventos recebidos/filtrados
- intenções extraídas
- tempo de resolve da Memoria.ia
- tokens de entrada/saída
- modelo/provedor
- TTFT
- tempo até primeiro áudio
- custo estimado
- deltas aceitos/rejeitados
- Continuity Error Rate (CER)
