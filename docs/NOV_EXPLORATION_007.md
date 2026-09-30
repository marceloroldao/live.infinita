# NOV Exploration 007 — deterministic anti-backtracking

## Problema observado

Após a topologia persistente 006 entrar em produção, o World State passou a
conter as 12 regiões e o SpatialSession expôs corretamente novos vizinhos.
Mesmo assim, o `NpcIdleWander` permaneceu em um ciclo curto:

`clearing → shelter → clearing → shelter`.

A causa era a combinação entre o bucket global e o índice determinístico do
vizinho. A topologia estava correta; o seletor podia voltar imediatamente pela
mesma aresta e repetir para sempre.

## Solução

Travessias idle passam a carregar `navigation_context`:

- `previous_region_id`: região da qual o NPC saiu;
- `arrived_region_id`: região na qual o movimento entrou.

O `AgentIntentResolver` converte esse contexto no mesmo delta canônico do
`move_to_position`, gravando:

- `properties.navigation.previous_region_id`;
- `properties.navigation.arrived_region_id`.

A autoridade continua `entity_agent` e todas as operações atingem apenas o
próprio NOV. Nenhuma permissão adicional é necessária.

Ao escolher a próxima aresta, `NpcIdleWander` usa o ponteiro anterior somente
quando `arrived_region_id` ainda coincide com a região atual. Se houver mais
de um vizinho, a aresta de retorno imediato é removida das opções. Se o
contexto estiver obsoleto por causa de outro tipo de movimento, ele é ignorado.

## Propriedades

- determinístico;
- sem RNG;
- sem LLM;
- sem varrer `plans.jsonl`;
- sem estado volátil em RAM;
- persistente e replayável;
- cede normalmente para necessidades e planos de prioridade maior.

## Gate

`tests/test_nov_exploration_007.py` executa o algoritmo real sobre a topologia
base de 12 regiões. Partindo de `shelter`, a caminhada determinística deve
alcançar todas as 12 regiões e não pode voltar imediatamente pela mesma aresta
quando existir alternativa.

Os testes do protocolo também exigem que `navigation_context` vire um delta
`move + set + set`, autorizado pelo `MutationGate` para o próprio
`subject_entity_id`, e rejeitam contexto cujo `arrived_region_id` não
coincida com o destino do movimento.
