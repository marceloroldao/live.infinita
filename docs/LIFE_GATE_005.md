# Life Gate 005 — Distributed Water Quantity

## Objetivo

Evoluir Água de um único agente espacial indivisível para uma quantidade ambiental
distribuída entre múltiplas regiões, mantendo conservação explícita e a mesma fronteira
entre World State e Memoria.ia.

## Novo estado do agente

Água continua sendo uma única entidade lógica, mas passa a possuir:

```text
environmental_distribution
  initial_total
  by_region
  evaporated_total
```

Exemplo inicial:

```text
initial_total = 100
by_region = { spring: 100 }
evaporated_total = 0
```

A posição única em `transform.region_id` deixa de definir presença física.

## Runtime distribuído

`distributed_environment_runtime.py` processa um snapshot da distribuição existente no
início de cada tick.

Para cada região:

```text
before
  = retained
  + transferred
  + evaporated
```

As quantidades transferidas neste tick só podem ser processadas novamente no tick
seguinte. Isso impede cascatas instantâneas artificiais.

## Política world-owned

O runtime não conhece semântica especial de Água. A regra informa apenas:

- componente da distribuição;
- propriedade regional usada como retenção;
- propriedade regional usada como evaporação;
- propriedade da rota usada como capacidade;
- intervalo mínimo entre ticks.

As propriedades vivem no World State.

## Cenário do gate

Estado inicial:

```text
spring: 100
evaporated: 0
```

Propriedades de `spring`:

```text
retention_units = 20
evaporation_units = 10
```

Rotas simultâneas:

```text
spring -> channel capacity 40
spring -> hollow  capacity 30
```

Após o primeiro tick:

```text
spring: 20
channel: 40
hollow: 30
evaporated: 10
total conserved: 100
```

No segundo tick, os três estoques existentes são processados independentemente:

```text
spring: 10
channel: 10
hollow: 15
basin: 37
evaporated_total: 28
total conserved: 100
```

O valor em `basin` resulta de fluxos concorrentes vindos de `channel` e `hollow`.

## Percepção e co-localização

`environmental_perception.py` e o guard de ações do World Runtime passam a aceitar
agentes ambientais distribuídos.

Água pode estar presente simultaneamente em:

```text
spring
channel
hollow
```

Nov pode interagir com a mesma entidade `water_01` em qualquer região cuja quantidade
seja maior que zero.

Os Gates anteriores continuam compatíveis com agentes de posição única.

## Fronteira cognitiva

Nesta etapa, Nov percebe presença, não quantidade exata.

A Memoria.ia recebe:

- região observada;
- presença/ausência de Água;
- intervenções disponíveis;
- consequências observadas.

Ela não recebe:

- `initial_total`;
- `by_region`;
- `evaporated_total`;
- valores 100/40/30/20 etc.;
- regras internas de balanço.

Isso permite testar física quantitativa sem entregar a variável oculta diretamente à
cognição.

## Gate cross-repo

1. Nov encontra Água em `spring`.
2. Duas observações estabelecem o regime situado.
3. O primeiro tick distribuído divide Água entre três regiões e evapora parte.
4. A Memoria.ia permanece inalterada pelo tick ambiental.
5. Como ainda existem 20 unidades em `spring`, o contexto conhecido continua válido.
6. Nov não precisa reexplorar Água em `spring`.
7. Nov desloca-se para `channel`.
8. A mesma entidade Água está presente ali.
9. O novo contexto situado volta a gerar curiosidade.
10. Uma observação em `channel` fica pendente.
11. O segundo tick gera fluxo concorrente para `basin`.
12. O balanço global continua exatamente conservado.
13. Nov pode encontrar Água também em `basin`.

## Invariantes

- nenhuma quantidade pode ficar negativa;
- `sum(by_region) + evaporated_total == initial_total`;
- cada balanço regional fecha exatamente;
- inflow novo não é reprocessado no mesmo tick;
- movimento distribuído não escreve Memoria.ia;
- quantidade exata não vaza para `state_addresses`;
- presença multi-região é read-only;
- ações continuam world-bounded;
- execução é determinística.

## Próxima evolução

O Life Gate 006 pode adicionar percepção quantitativa indireta: Nov não receberia o
valor interno de volume, mas sensores poderiam produzir intensidades observáveis
discretizadas ou contínuas, permitindo aprender relações entre nível, fluxo,
retenção e consequências sem expor o estado oculto do simulador diretamente.
