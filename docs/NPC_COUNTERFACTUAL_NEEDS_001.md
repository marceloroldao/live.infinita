# NPC Counterfactual Needs 001

## Objetivo

Estender a simulacao contrafactual deterministica para projetar, em shadow state, a evolucao interna de `safety`, `energy`, `social` e `curiosity` durante cada estrategia candidata.

A projeção continua estritamente nao autoritativa: ela nao modifica World State, Need Dynamics, Proposal Ledger, Plan Ledger ou Mutation Gate.

## Regra epistemica

O simulador pode estimar **custos internos futuros**, mas nunca aplicar satisfacao imaginada.

Exemplo:

- uma rota longa pode aumentar `energy`;
- uma rota exposta pode aumentar `safety`;
- uma espera longa pode aumentar `social` e `curiosity`;
- chegar imaginariamente a uma cama nao reduz `energy`.

A reducao de uma necessidade continua ocorrendo exclusivamente apos um outcome real de plano concluido.

## Dinamica projetada

A projecao usa as mesmas taxas basicas do `NpcNeedDynamics`:

- `safety`: `-0.003 + effective_risk * 0.020` por tick;
- `energy`: `+0.002` por tick;
- `social`: `+0.0015` por tick;
- `curiosity`: `+0.0010` por tick.

A protecao contrafactual de uma estrategia reduz apenas o risco efetivo usado para projetar `safety`.

## Custo interno projetado

O shadow state produz `projected_need_cost`, calculado apenas sobre aumentos das necessidades em relacao ao snapshot inicial, com pesos relativos:

- safety: `1.00`;
- energy: `0.70`;
- social: `0.40`;
- curiosity: `0.20`.

O `NpcCompositeStrategy` aplica um `projected_need_weight` limitado (baseline `0.20`) ao valor esperado de estrategias ainda sem experiencia empirica madura.

## Precedencia

A ordem de confianca permanece:

1. experiencia empirica madura da estrategia;
2. evidencia observada e outcomes reais;
3. counterfactual + causal forecast;
4. heuristicas estaticas.

Quando uma estrategia possui experiencia empirica madura, o custo interno contrafactual nao altera seu ranking.

## Auditoria

Cada counterfactual v2 inclui:

- `start_needs`;
- `end_needs`;
- `projected_need_cost`;
- `needs_before` e `needs_after` em cada fase;
- risco efetivo por fase;
- transicoes temporais previstas;
- `mutates_world=false`.

## Invariante principal

> Imaginar uma consequencia pode alterar uma escolha; nunca pode ser confundido com a consequencia ter acontecido.
