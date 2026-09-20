# Life Gate 008 — Temporal RealitySlice Bridge

## Objetivo

Conectar a trajetória sensorial da Live.infinita ao experimento temporal multimodal já
existente no `bit.analyze`, sem duplicar o algoritmo de associação e sem escrever
relações semânticas manualmente na Memoria.ia.

O Gate 008 transforma uma janela de frames sensoriais sincronizados em uma única
`RealitySlice` temporal.

## Dependência cross-repo

Implementação temporal usada:

```text
marceloroldao/bit.analyze
branch: experiment/temporal-multimodal-reality-slice
validated commit: b39de5704e07c86c374d62fe8c43eda1d04a9ac8
experiments/temporal_multimodal/reality_slice.py
```

A Live.infinita não reimplementa:

- reforço por proximidade;
- direção temporal;
- recorrência;
- estatística de deslocamento temporal;
- consolidação;
- esquecimento.

Ela apenas adapta os frames observáveis para o contrato `RealitySlice`.

## Por que uma janela e não uma slice por frame

O `TemporalAssociator` aprende relações entre ocorrências dentro de uma
`RealitySlice`.

Portanto:

```text
Frame A -> slice A
Frame B -> slice B
Frame C -> slice C
```

não preservaria diretamente as transições A→B→C no mesmo espaço de associação.

O Gate usa:

```text
RealitySlice
  Frame A
    ↓ Δt
  Frame B
    ↓ Δt
  Frame C
```

Assim os padrões dos três frames coexistem numa única janela temporal e mantêm seus
deslocamentos relativos.

## Política da janela no World State

O cenário declara:

```text
frame_count         = 3
tick_seconds        = 0.10
occurrence_duration = 0.02
```

Esses parâmetros não ficam escondidos no código do experimento.

## Padrões opacos

Cada leitura consolidada gera um ID inteiro determinístico a partir de:

```text
(sensor_id, band_id)
```

Exemplos conceituais:

```text
(s_intensity, i2) -> pattern_id A
(s_intensity, i1) -> pattern_id B
(s_flow, d1)      -> pattern_id C
```

O hash não inclui:

- significado da faixa;
- quantidade física;
- world_id;
- episódio;
- posição temporal.

Logo, o mesmo padrão observável mantém a mesma identidade em episódios independentes.

## Modalidade

Todos os sinais atuais usam:

```text
Modality.SENSOR
```

Isso é intencional.

Os quatro canais do Gate 007 são canais do mesmo sistema sensorial, não modalidades
físicas diferentes. O Gate não marca intensidade como AUDIO ou tendência como VISUAL
artificialmente.

Quando visão, áudio, toque ou texto reais entrarem, o mesmo contrato do `bit.analyze`
poderá representá-los com suas modalidades corretas.

## Trajetória usada

Cada episódio produz:

### Frame 0

```text
p1 / i2 / t0 / d0
```

### Frame 1

```text
p1 / i1 / t2 / d1
```

### Frame 2

```text
p1 / i0 / t2 / d0
```

A janela contém:

```text
3 frames × 4 canais = 12 ocorrências
```

Os centros temporais preservam a distância lógica dos frames.

## Identidade de episódio

Dois episódios independentes usam `slice_id` diferentes.

Os `pattern_id`, porém, permanecem iguais para os mesmos sinais.

Isso permite que o `TemporalAssociator` reconheça recorrência sem confundir replay da
mesma slice com nova evidência independente.

## Proximidade temporal

O Gate compara, por exemplo:

```text
i2(frame 0) -> i1(frame 1)
```

com:

```text
i2(frame 0) -> i0(frame 2)
```

Como a primeira associação está temporalmente mais próxima, ela deve adquirir
`rho` maior após o mesmo número de episódios.

Nenhuma regra diz que `i2` está relacionado a `i1`. A diferença nasce apenas da
distância temporal.

## Direção

O associador registra:

- forward;
- simultaneous;
- backward;
- mean_dt;
- variance_dt.

Como a chave interna ordena IDs numéricos, forward/backward é interpretado em relação à
ordem dos pattern IDs. O gate verifica a orientação correta sem atribuir significado
semântico aos IDs.

## Repetição

Episódios independentes com a mesma transição observável devem:

```text
repetitions: 1 -> 2 -> ...
rho: aumentar de forma saturante
```

O mesmo `slice_id` não é reutilizado para simular repetição.

## Consolidação e esquecimento

O Gate usa o mecanismo já existente do `bit.analyze`:

```text
mais repetições
    ↓
maior consolidação
    ↓
menor taxa efetiva de esquecimento
```

Uma associação observada em dez episódios deve reter mais `rho` depois de um longo
intervalo que a mesma associação observada uma única vez.

## Fronteira com Memoria.ia

Neste gate:

```text
World State
   ↓
frames sensoriais
   ↓
RealitySlice
   ↓
TemporalAssociator (bit.analyze)
```

Ainda não existe escrita automática dessas associações na Memoria.ia.

O teste exige:

- bridge read-only sobre o World State;
- física não escreve Memoria.ia;
- amostragem não escreve Memoria.ia;
- associação temporal não escreve Memoria.ia.

Isso mantém a separação:

```text
bit.analyze = descobrir estrutura temporal
Memoria.ia  = persistir/usar estado cognitivo quando o contrato estiver maduro
```

## Invariantes

- 3 frames formam uma única RealitySlice;
- 4 canais por frame permanecem independentes;
- todas as ocorrências atuais são `Modality.SENSOR`;
- pattern IDs são determinísticos;
- pattern IDs são estáveis entre episódios;
- slice IDs são independentes entre episódios;
- distância temporal afeta `rho`;
- direção temporal é registrada;
- repetição independente reforça a associação;
- consolidação reduz esquecimento;
- bridge não muta World State;
- associador não escreve Memoria.ia;
- replay é determinístico.

## Próxima evolução

O Life Gate 009 pode introduzir uma camada de seleção/colapso entre as associações
temporais do `bit.analyze` e a Memoria.ia.

A proposta é não copiar todas as arestas aprendidas. Somente estruturas com evidência
suficiente — recorrência independente, estabilidade temporal, seletividade e
proveniência — seriam transformadas em eventos estruturais candidatos para a
Memoria.ia, ainda sem declarar seu significado semântico.
