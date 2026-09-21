# Life Gate 004 — Water reacts to local world properties

## Objetivo

Evoluir Água de uma rota fixa para um agente ambiental que escolhe seu próximo caminho
a partir de propriedades locais declaradas no World State.

O runtime permanece genérico. Ele não contém significado especial para:

- capacidade;
- inclinação abstrata;
- retenção;
- evaporação.

Esses nomes existem apenas como propriedades numéricas do mundo e como uma política
ordinal declarada na própria regra do agente ambiental.

## Arquitetura

Cada região pode expor rotas ambientais:

```text
region
  -> environmental_routes[]
      -> route_id
      -> to_region
      -> trace_address
      -> properties {}
```

Uma regra reativa declara somente a ordem de comparação:

```text
capacity   desc
descent    desc
retention  asc
evaporation asc
```

O runtime apenas aplica essa ordenação de forma determinística. Alterar os valores no
World State deve alterar a escolha da rota sem alterar código.

## Atualização autoritativa das propriedades

`world_property_runtime.py` fornece uma primitive genérica para substituir propriedades
de uma rota. A alteração:

- incrementa tick/version;
- cria Event;
- cria Delta;
- preserva o estado anterior no histórico;
- não toca na Memoria.ia.

## Cenário

Na região `spring` existem duas saídas:

```text
spring_channel
  capacity=8
  descent=6
  retention=2
  evaporation=3

spring_hollow
  capacity=5
  descent=4
  retention=7
  evaporation=1
```

No estado inicial, Água escolhe `spring_channel`.

Durante o gate, apenas as propriedades são alteradas:

```text
spring_channel.capacity = 2
spring_hollow.capacity  = 9
```

Sem modificar o código do runtime, a próxima transição deve passar a escolher
`spring_hollow`.

## Relação com Nov e Memoria.ia

As propriedades internas da rota são estado oculto do mundo para a cognição de Nov.

A Memoria.ia recebe somente o que Nov pode observar estruturalmente:

- região atual;
- presença de Água;
- relações projetadas;
- intervenção disponível;
- consequências observadas.

Os nomes `capacity`, `descent`, `retention` e `evaporation` não podem aparecer em
`state_addresses`.

## Gate cross-repo

1. Nov encontra Água em `spring`.
2. Duas observações estabelecem o regime situado local.
3. As propriedades das rotas mudam via World State.
4. A Memoria.ia permanece inalterada.
5. O runtime reativo move Água para `hollow`.
6. Em `spring`, Nov não pode mais executar `probe`.
7. Nov desloca-se para `hollow`.
8. Água reaparece na projeção cognitiva.
9. O regime situado de `spring` não é reutilizado como continuidade local.
10. A transferência estrutural pode produzir ambiguidade, levando curiosidade a
    executar novo `probe`.
11. Uma única observação em `hollow` permanece pendente.
12. O trace ambiental preserva as propriedades da rota efetivamente escolhida.

## Invariantes

- nenhum nome de propriedade possui lógica hardcoded no runtime;
- mudança de propriedade é autoritativa e append-only;
- Memoria.ia não recebe diretamente propriedades ocultas;
- movimento ambiental não escreve memória cognitiva;
- ação de Nov continua limitada ao World Runtime;
- percepção ambiental continua read-only;
- seleção de rota é determinística;
- alterar somente o World State pode alterar o caminho de Água.

## Próxima evolução

Depois deste gate, o Life Gate 005 pode transformar o agente Água de um único corpo
discreto em quantidade distribuível entre regiões, permitindo retenção parcial,
evaporação e fluxo concorrente sem abandonar a mesma fronteira arquitetural.
