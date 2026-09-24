# Plan Ledger + Scheduler 001

## Objetivo

Persistir planos derivados de intenções e executá-los de forma determinística, um passo por tick, sem depender de uma LLM durante a execução.

## Lifecycle

Estados canônicos do plano:

- `planned`
- `running`
- `waiting`
- `replanning`
- `completed`
- `failed`
- `cancelled`

Estados terminais: `completed`, `failed`, `cancelled`.

## Separação de responsabilidades

`DeterministicIntentPlanner` cria o plano sem mutar o mundo.

`PlanLedger` persiste plano, cursor (`next_step_index`) e evidências de passos concluídos.

`PlanScheduler.tick(plan_id)` executa no máximo um passo.

Cada passo:

1. revalida o estado autoritativo esperado;
2. resolve a intenção do passo em operações canônicas;
3. passa pela Mutation Gate;
4. grava mutation decision;
5. aplica no Cold Engine;
6. registra world event/state hash;
7. só então avança o cursor persistente.

## Invariante de retomada

O cursor só avança depois do commit autoritativo confirmado. Após restart, um novo scheduler lê `plan-ledger.jsonl` e continua em `next_step_index`.

Isso impede repetir um passo já confirmado ou pular um passo ainda não confirmado.

## Divergência

Se o ator não estiver na região esperada para o próximo passo, o scheduler não improvisa. O plano entra em `replanning` mantendo o cursor no passo não executado.

Uma camada futura de replanning deverá criar uma nova rota a partir do estado atual e registrar explicitamente a revisão do plano.

## Cadência

Esta revisão não inicia um loop automático no servidor. O scheduler expõe execução por `tick()` e `tick_all()` para que a política de cadência seja decidida separadamente.

## Exemplo

Objetivo: `Nov quer ir até bridge`.

Plano persistido:

`r0 -> r1 -> r2 -> posição final da bridge`

Tick 1: waypoint r1.

Tick 2: waypoint r2.

Tick 3: posição final da bridge.

Cada tick produz sua própria Mutation Decision, World Event, Delta e State Hash.

## Escalabilidade

Planos persistem apenas intenção, rota, passos e referências de auditoria. Eles não carregam o mundo nem entidades cold para RAM.
