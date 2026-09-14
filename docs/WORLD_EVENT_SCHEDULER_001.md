# World Event Scheduler 001

## Objetivo

Adicionar eventos temporais persistentes ao relógio lógico da Live.infinita sem
acoplar causalidade ao relógio real do servidor ou ao FPS do renderer.

## Modelo

Um evento agendado contém:

- `scheduled_event_id`
- `due_tick`
- operações canônicas
- principal/proveniência
- narração opcional
- metadados
- recorrência opcional em ticks
- status e último resultado autoritativo

Estados terminais:

- `fired`
- `cancelled`
- `failed`

Eventos recorrentes permanecem `scheduled` e avançam seu `due_tick` após cada
disparo confirmado.

## Ordem dentro de um World Tick

1. `SimulationClock.advance()`
2. eventos vencidos do novo tick
3. planos ativos em ordem determinística de `plan_id`

A ordem é deliberada. Um evento global que vence no tick N (por exemplo, chuva)
pode afetar o estado observado por personagens que também executam um passo no
tick N.

## Autorização

Agendamento não concede autoridade. No disparo, as operações passam por:

`WorldEventScheduler -> GuardedMutationService -> MutationGate -> Cold Engine`

Uma rejeição da Gate marca o evento como `failed` e não altera o mundo.

## Exemplos

Chuva no tick 1200:

```json
{
  "due_tick": 1200,
  "operations": [
    {"op": "set_world", "path": ["environment", "weather"], "value": "rain"}
  ]
}
```

Fogueira apagar 80 ticks depois:

```json
{
  "due_tick": 2080,
  "operations": [
    {"op": "set", "entity_id": "fire_01", "path": ["properties", "lit"], "value": false}
  ]
}
```

Evento recorrente a cada 100 ticks usa `recurrence_every_ticks=100`.

## Sem catch-up explosivo

O Tick Driver continua sendo a única fonte de avanço lógico. Downtime do servidor
não gera milhares de ticks retroativos. Além disso, uma chamada `fire_due(tick)`
executa cada evento agendado no máximo uma vez naquela chamada, mesmo se uma
recorrência estiver numericamente atrasada.

## Persistência

O ledger é append-only JSONL. Reiniciar o processo preserva:

- tick de vencimento
- estado do evento
- contagem de disparos
- último `mutation_decision_id`
- último `world_event_id`
- último `state_hash`

## Escopo v1

O scheduler recebe operações canônicas. Uma evolução posterior poderá agendar
intenções semânticas que sejam resolvidas somente no tick de execução.
