# Life Gate 003 — Water as a Persistent Environmental Agent

## Objetivo

Substituir a fonte ambiental estática dos gates anteriores pelo primeiro agente
ambiental persistente da Live.Infinita.

Água passa a possuir:

- identidade estável no World State;
- estado espacial próprio;
- relógio lógico de transição;
- geração/continuidade própria;
- regras de deslocamento declaradas pelo mundo;
- Event/Delta a cada tick ambiental;
- traços persistentes deixados nas regiões anteriores.

A Memoria.ia continua sem receber semântica especial de Água. Para o núcleo cognitivo,
`water_01`, regiões, intervenções e consequências continuam sendo endereços.

## Nova fronteira ambiental

O arquivo `environmental_agent_runtime.py` implementa uma primitive genérica:

```text
World(t)
  -> environmental scheduler
  -> verifica agentes ambientais ativos
  -> aplica transições world-owned habilitadas pelo tick lógico
  -> grava Event + Delta
  -> atualiza estado espacial do agente
  -> deixa environmental_trace persistente
  -> World(t+1)
```

O runtime não contém regra específica de água. Ele lê regras do World State:

```text
agent
from_region
to_region
min_ticks
trace_address
```

Vento e Vegetação poderão posteriormente usar o mesmo boundary.

## Percepção ambiental

A presença de um agente ambiental próximo à Nov é uma projeção cognitiva derivada do
estado espacial.

`environmental_perception.py` cria uma relação read-only somente no frame cognitivo:

```text
Nov + Water no mesmo region_id
  -> co_located_with
```

A relação não é persistida artificialmente no World State. Quando Água muda de região,
o frame seguinte é reconstruído e a relação desaparece naturalmente.

## Ações condicionadas ao mundo

O World Runtime passa a aceitar o guard genérico:

```text
requires_target_colocation = true
```

Assim, uma ação sobre um alvo só é oferecida se ator e alvo ativos estiverem na mesma
região. A Memoria.ia não pode forçar uma interação com Água que não esteja presente.

## Cenário

Estado inicial:

```text
Nova:  spring
Water: spring
```

Fluxo ambiental:

```text
spring --4 ticks--> stream --2 ticks--> basin --3 ticks--> spring
```

Cada saída deixa um trace persistente na região abandonada.

## Gate

1. Nov encontra Água em `spring`.
2. Curiosidade executa duas observações independentes.
3. O regime situado de `spring` é estabelecido.
4. Sem nova ação da Nov, ticks ambientais avançam.
5. Água move-se de `spring` para `stream`.
6. A Memoria.ia não é alterada pelo movimento ambiental.
7. Em `spring`, a ação `probe` deixa de estar disponível.
8. O frame cognitivo da Nov deixa de conter `water_01`.
9. Nov desloca-se para `stream`.
10. A presença de Água reaparece no frame cognitivo.
11. O regime situado de `spring` não é reutilizado como continuidade local.
12. A estrutura aprendida pode transferir, mas como os dois resultados possíveis são
    estruturalmente equivalentes como endereços novos, o estado permanece ambíguo.
13. Curiosidade volta a escolher `probe`.
14. Uma única observação em `stream` fica pendente e ainda não estabelece novo regime.
15. Água move-se autonomamente para `basin`.
16. O mundo contém traces persistentes em `spring` e `stream`.

## Invariantes

- movimento ambiental não escreve na Memoria.ia;
- percepção ambiental é read-only;
- a ação sobre Água existe somente quando há co-localização;
- nenhuma LLM participa;
- movimento ambiental independe de ação da Nov;
- World State continua autoritativo;
- Event/Delta são append-only;
- regimes situados não vazam entre regiões concretas;
- transferência estrutural continua possível;
- execução completa deve ser determinística.

## Próxima evolução

Se este gate passar, o próximo passo é Life Gate 004: Água deixa de apenas se deslocar
por uma rota fixa e passa a reagir a propriedades locais do mundo, como capacidade,
inclinação abstrata, retenção e evaporação, ainda usando regras world-owned e sem
semântica no núcleo da Memoria.ia.
