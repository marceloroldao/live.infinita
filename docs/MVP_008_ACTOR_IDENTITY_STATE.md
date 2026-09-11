# MVP-008 — Actor / Identity State

## Objetivo
Criar uma camada persistente de identidade observada para participantes vindos de TikTok, YouTube, API, simulator e outras fontes futuras, sem fundir automaticamente identidades entre plataformas.

## Chave de identidade
Cada ator usa uma chave namespaced:

`source:actor_id`

Exemplos:
- `tiktok:alice`
- `youtube:alice`

Essas duas chaves permanecem distintas. Uma futura camada de resolução de identidade poderá propor vínculos com proveniência e evidência explícita.

## Persistência
Observações são append-only em:

`/var/lib/live-infinita/actor-observations.jsonl`

O estado atual do ator é derivado por fold das observações.

## Estado derivado
Cada ator expõe:
- `actor_key`
- `source`
- `actor_id`
- `display_name` atual
- `display_names_seen`
- `first_seen_unix`
- `last_seen_unix`
- `interactions_total`
- `interactions_by_kind`
- `last_interaction`
- `entity_id` reservado para vínculo futuro com personagem do mundo

## Fontes de observação
- comentários e demais eventos que passam pelo Gateway;
- join / like / gift do side channel de audiência;
- backfill dos logs históricos existentes na primeira inicialização desta versão.

## Endpoints
- `GET /api/actors`
- `GET /api/actors/{source}/{actor_id}`

## Princípio arquitetural
Actor State não é World State. Observar ou atualizar a identidade de um participante não altera `world.version`, `world.sequence` ou `state_hash`.

## Critério de validação
1. health mostra `mvp=008`, `version=0.9.0` e `replay_ok=true`;
2. testes de ActorStore passam;
3. `/api/actors` recupera participantes históricos por backfill;
4. um novo join ou comentário atualiza o mesmo ator sem criar identidade duplicada;
5. o mesmo `actor_id` em TikTok e YouTube gera duas identidades distintas;
6. `/api/replay/verify` permanece `ok=true`.

## Ordem temporal e recuperação
O fold ordena pelo `observed_at_unix`; empates preservam a ordem de append.
Uma observação antiga recebida depois não substitui nome/última interação mais recentes.
Novos comandos aceitos pelo Gateway preservam esse horário no contexto do evento do
runtime, permitindo reconstruir a mesma cronologia no backfill.

Eventos antigos do runtime não possuem horário real. Nesses casos, mantém-se o
horário da recuperação, identificado por `metadata.timestamp_basis=backfill` na
observação. Esses horários não devem ser interpretados como a data original da
interação. Observações já persistidas não são reescritas. Comentários rejeitados
anteriores ao MVP-008 não podem ser recuperados dos logs do runtime.

## Testes e VM
Ver [roteiro Ubuntu](MVP_008_VM_VALIDATION.md). A suíte usa diretórios temporários;
o verificador HTTP consulta apenas por padrão e exige `--write` para criar dados.
