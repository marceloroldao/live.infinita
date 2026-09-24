# Intent Planning 001

## Objetivo

Executar objetivos semânticos de agentes sem controle frame a frame pela IA.

Exemplo:

`Nov quer ir até a ponte`

vira um plano determinístico sobre a topologia persistente de regiões.

## Fluxo

```text
semantic intent
  -> DeterministicIntentPlanner
  -> region route
  -> revalidatable plan steps
  -> AgentIntentResolver
  -> canonical operations
  -> Mutation Gate
  -> authoritative event/delta per step
```

Planejamento não concede autoridade. Cada passo continua sujeito à Mutation Gate.

## Movimento entre regiões

Para `move_to_entity` e `move_to_position`, o planner usa `RegionCatalog.route()`.

Exemplo:

```text
r0 -> r1 -> r2
```

produz:

1. mover ator para waypoint determinístico no centro de `r1`;
2. mover ator para waypoint determinístico no centro de `r2`;
3. executar o objetivo final, por exemplo alcançar a posição atual da ponte.

O último passo resolve o alvo novamente no `AgentIntentResolver`, portanto usa o estado autoritativo disponível no momento da execução.

## Revalidação

Cada `PlanStep` registra `expected_region_id`.

Imediatamente antes da execução:

```text
actor.region_id == expected_region_id
```

Se a condição não for verdadeira, o executor retorna `stale` e não improvisa o próximo passo.

Isso permite que outro evento do universo invalide uma rota sem causar teleporte ou mutação baseada em premissa antiga.

## Estados do executor

- `completed`: todos os passos foram aceitos e commitados;
- `rejected`: Mutation Gate recusou um passo;
- `stale`: estado autoritativo divergiu do plano;
- `invalid`: a resolução semântica do passo falhou.

## Replay e proveniência

Cada passo aceito produz seu próprio:

- `mutation_decision_id`;
- `world_event_id`;
- delta;
- evolução do state hash.

Logo uma viagem longa é auditável como uma sequência causal de mudanças, e não como uma mutação opaca única.

## Custo

O plano guarda apenas a rota de regiões e os intents de passo. Não materializa o mundo inteiro e não altera a arquitetura hot/warm/cold.

## Próxima evolução

- `Plan Ledger` persistente para planos longos;
- execução incremental/tick em vez de executar todos os passos em uma chamada;
- condições e obstáculos explícitos;
- replanning determinístico quando o plano fica `stale`;
- integração com scheduler de agentes.
