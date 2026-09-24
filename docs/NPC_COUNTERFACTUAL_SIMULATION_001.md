# NPC Counterfactual Simulation 001

## Objetivo

Permitir que um NPC compare estratégias possíveis em um estado-sombra compacto antes de escolher uma ação real.

O simulador não clona o mundo autoritativo, não chama Mutation Gate e não escreve World State. Ele projeta apenas variáveis necessárias à comparação: tick lógico, transições de período previstas, risco, proteção por fase e duração estimada.

## Fluxo

```text
estratégias candidatas
    -> NpcCounterfactualSimulator
    -> shadow trace por fase
    -> mean/peak effective risk
    -> NpcCompositeStrategy ranking
    -> estratégia escolhida
    -> execução real continua passando por PlanScheduler + Mutation Gate
```

## Shadow state

Cada projeção contém:

- `start_tick` / `end_tick`;
- `start_period` / `end_period`;
- `start_risk`;
- `mean_effective_risk`;
- `peak_effective_risk`;
- trace fase a fase;
- causal forecast usado, quando aplicável;
- `mutates_world=false`.

## Estratégias iniciais

- `direct` — exposição total ao risco previsto;
- `via_shelter:<id>` — proteção parcial enquanto passa pelo abrigo;
- `wait_then_direct` — espera no estado-sombra e depois desloca.

A proteção é uma heurística explícita e auditável. Ela não é verdade física nem regra de autoridade do mundo.

## Precedência epistemológica

Quando a experiência empírica completa da estratégia já está madura, o ranking usa os dados observados e não aplica o contrafactual como substituto da evidência real.

```text
experiência empírica madura
    > contrafactual + causal forecast
    > heurística estática
```

## Invariantes

1. O simulador nunca muta o mundo real.
2. Não cria eventos, planos ou proposals.
3. O horizonte é limitado (`max_steps`).
4. A saída é determinística para os mesmos inputs.
5. A trilha completa fica disponível no ranking para auditoria.
6. Toda ação escolhida continua sujeita ao fluxo autoritativo normal.

## Interpretação

A camada representa uma simulação contrafactual simples:

- "se eu for direto..."
- "se eu passar pelo abrigo..."
- "se eu esperar e depois for..."

Ela é um world model interno mínimo e determinístico, não uma simulação paralela completa do mundo.
