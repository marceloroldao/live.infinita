# Life Gate 006 — Indirect Quantitative Sensing

## Objetivo

Permitir que Nov perceba mudanças quantitativas da Água sem expor diretamente o volume
interno do simulador para a Memoria.ia.

A física continua autoritativa no World State. O sensor converte quantidade local oculta
em uma faixa observável, com ruído, histerese e persistência.

## Sensor autoritativo

`environmental_sensor_runtime.py` separa duas operações:

1. `sample_environmental_sensors()`
   - lê a quantidade ambiental oculta;
   - aplica ruído determinístico;
   - calcula uma faixa candidata;
   - aplica histerese;
   - exige persistência por múltiplas amostras;
   - grava o estado sensorial via Event/Delta.

2. `project_environmental_sensor_readings()`
   - é read-only;
   - projeta apenas a faixa sensorial consolidada;
   - nunca projeta valor bruto, valor com ruído ou volume interno.

A decisão cognitiva nunca amostra o sensor implicitamente.

## Configuração do Gate

O sensor local da Nov usa:

```text
sensor_id            = water_local_level
noise_amplitude      = 2
hysteresis           = 3
persistence_samples  = 2

q0: min 0
q1: min 15
q2: min 35
```

Os IDs das faixas são apenas categorias de observação. A Memoria.ia não recebe os
limites numéricos.

## Fluxo principal

No início:

```text
spring water = 100
sensor -> q2
```

Nov observa duas vezes e estabelece um regime situado para esse contexto.

Depois do primeiro tick distribuído do Life Gate 005:

```text
spring water = 20
```

Primeira nova amostra:

```text
candidate = q1
committed = q2
pending   = q1 (1/2)
```

A percepção consolidada ainda é q2. Portanto:

- o contexto cognitivo continua sendo o contexto aprendido;
- a previsão continua resolvida;
- curiosidade não volta a executar probe.

Segunda amostra consistente:

```text
candidate = q1
committed = q1
pending   = none
```

Agora a identidade estrutural da leitura muda. Portanto:

- o contexto situado muda;
- o regime q2 não vaza para q1;
- a estrutura histórica ainda pode transferir ambiguidade;
- curiosidade volta a selecionar probe;
- uma única observação em q1 permanece pendente.

## Ruído determinístico

O ruído é derivado de:

```text
world_id
sensor_id
observer_id
tick_id
raw_value
```

Assim o mesmo snapshot produz a mesma leitura. Replay permanece determinístico.

## Histerese

Uma leitura próxima a uma fronteira não alterna imediatamente entre faixas.

Exemplo:

```text
q2 começa em 35
histerese = 3

leitura = 34
estado anterior = q2
resultado = permanece q2
```

## Persistência

Mesmo quando a leitura já atravessou claramente a zona de histerese, uma nova faixa
precisa aparecer em duas amostras consecutivas antes de ser consolidada.

Isso evita que uma única perturbação gere nova realidade cognitiva.

## Fronteira cognitiva

O World State pode armazenar internamente:

- `raw_value`;
- `noisy_value`;
- quantidade por região;
- volume inicial;
- total evaporado;
- limiares;
- histerese;
- contadores de persistência.

A projeção cognitiva contém apenas uma entidade opaca correspondente à faixa sensorial
consolidada.

Duas quantidades ocultas diferentes dentro da mesma faixa devem produzir exatamente o
mesmo `observer_state_addresses`.

## Invariantes

- amostragem é autoritativa e cria Event/Delta;
- projeção é read-only;
- decisão cognitiva não muda o sensor;
- ruído é determinístico;
- histerese evita chatter na fronteira;
- persistência exige evidência repetida;
- estado quantitativo exato não entra na Memoria.ia;
- mesma faixa observável implica mesmo estado cognitivo;
- mudança consolidada de faixa cria contexto situado diferente;
- amostragem não escreve na Memoria.ia;
- Gates 001–005 permanecem compatíveis.

## Próxima evolução

O Life Gate 007 pode abandonar faixas fixas como única representação e introduzir
múltiplos sensores independentes, por exemplo presença, intensidade, velocidade de
mudança e direção de fluxo. A Memoria.ia receberia padrões sensoriais combinados e
poderia descobrir relações temporais sem receber diretamente as variáveis físicas
ocultas.
