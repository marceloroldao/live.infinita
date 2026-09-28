# MVP-018A — Vida de Nov (leitura da memória episódica)

A página **Vida de Nov** no Manager mostra experiências efetivamente registradas pelo
`NpcEpisodicMemory` (`npc_episode_v1`). Ela **não** gera histórias sobre Nov nem infere
lembranças a partir da narração. O log já é escrito pelo processo autônomo quando um
resultado de estratégia é confirmado.

Fonte de produção: `/var/lib/live-infinita/autonomous-world/npc-episodes.jsonl`.
A rota protegida `GET /api/manage/nov/life` apresenta somente `npc_id=nov`,
`logical_tick`, necessidade, destino, estratégia, contexto limitado e resultado
(satisfação, risco observado, duração, preempções e replanejamentos).

## Segurança e fronteiras

- Consulta somente de leitura, feita em uma thread, nunca pelo Single Writer.
- Janela de leitura limitada a **256 KiB** e **256 registros**, exibindo até **8 episódios**.
  **Não** é uma contagem do histórico inteiro.
- Registros incompletos são ignorados. Episódios sem proveniência `npc_episode_v1`
  ou de outro NPC são rejeitados. IDs repetidos são exibidos uma única vez.
- `source` e campos textuais livres de contexto/resultado não entram na API.
- Sem gravação no World State, aprendizado, decisão, proposal, plano ou Memoria.ia.
- A página consulta a API a cada 15 segundos **somente enquanto estiver aberta**.
- Não é um endpoint público; exige o token do operador.

## Próxima integração com Memoria.ia

A ponte `CognitiveFrame` / Memoria.ia V2 e o Shadow Mode continuam separados.
Esta tela confirma **quais experiências reais já existem** antes de definir sincronização
com a instância central. Uma futura integração deverá versionar explicitamente a origem,
idempotência de `episode_id`, autenticação, confirmação de ingestão e reconciliação
offline, sem tornar a memória central a autoridade do World State.

O Godot continua renderizando normalmente; não há alteração na simulação.
