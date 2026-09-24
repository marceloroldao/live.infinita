# NPC Strategy Experience 001

## Objetivo

Aprender custo real de execução das estratégias dos NPCs usando tempo lógico e histórico de interrupções, sem rede neural e sem alterar o replay autoritativo do mundo.

## Métricas observadas

Para cada combinação `NPC + necessidade + alvo + contexto` o sistema mantém médias online de:

- `elapsed_ticks`: duração lógica real do plano;
- `preemptions`: quantas vezes o plano foi preemptado;
- `replans`: quantas revisões de rota foram necessárias;
- `observed_risk`: risco contextual observado na decisão.

A atualização é O(1) por outcome concluído.

## Tempo lógico

Planos registram `started_logical_tick` e `completed_logical_tick`. Nenhuma decisão de custo depende de `time.time()`.

`elapsed_ticks = completed_logical_tick - started_logical_tick + 1`

Se o servidor ficar parado, não existe catch-up artificial, porque o custo segue o Simulation Clock.

## Integração

`NpcNeedOutcomeProcessor` continua aplicando satisfação interna e aprendizado de recompensa. Quando um `NpcStrategyExperience` é configurado, o mesmo plano concluído alimenta também o custo observado.

`NpcStrategyValue` usa duas fontes:

1. `heuristic`: rota por regiões + risco conhecido, quando ainda não há experiência suficiente;
2. `empirical`: duração, interrupções e risco observados, após atingir `min_samples`.

A recompensa prevista continua vindo de `NpcNeedLearning`; custo e recompensa permanecem separados.

## Valor esperado

A avaliação passa a ser:

`expected_value = predicted_satisfaction - travel_penalty - risk_penalty - interruption_penalty`

Os pesos são configuráveis.

## Invariantes

- exploração determinística continua tendo precedência;
- custo empírico só substitui heurística quando há amostras suficientes;
- outcomes são idempotentes por `outcome_id`;
- planos antigos sem ticks lógicos continuam válidos, apenas não produzem experiência de custo;
- nenhum aprendizado concede autoridade de mutação;
- o planner autoritativo continua sendo a fonte da rota realmente executada.
