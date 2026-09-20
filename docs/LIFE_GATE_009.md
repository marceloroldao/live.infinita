# Life Gate 009 — Temporal Evidence Selector

## Objetivo

Criar a primeira fronteira explícita entre as associações temporais pré-semânticas do
`bit.analyze` e uma futura ingestão pela Memoria.ia.

O Gate 009 **não grava relações na Memoria.ia**.

Ele decide apenas se uma associação temporal possui evidência estrutural suficiente
para se tornar um **candidato transportável**.

## Por que não usar InterventionConsequenceMemory diretamente

A Memoria.ia V2 atual modela episódios explicitamente delimitados:

```text
estado -> intervenção -> consequência
```

Uma associação descoberta passivamente pelo `bit.analyze` não possui uma intervenção
real.

Inventar uma intervenção como:

```text
observe_temporal_relation
```

apenas para encaixar o dado na memória causal criaria uma causalidade fictícia e
violaria a separação arquitetural.

Por isso o Gate 009 termina antes da ingestão cognitiva.

## Entrada

O seletor recebe as associações do:

```text
bit.analyze TemporalAssociator
```

Cada associação já contém:

- `rho`;
- repetições;
- forward / simultaneous / backward;
- `mean_dt`;
- `variance_dt`;
- slices independentes observadas.

Além disso o engine calcula:

- seletividade;
- estabilidade temporal;
- evidence score.

## Política declarada no World State

O cenário define:

```text
min_repetitions            = 3
min_independent_slices     = 3
min_rho                    = 0.39
min_selectivity            = 0.80
min_temporal_stability     = 0.90
min_evidence_score         = 3.0
min_direction_confidence   = 0.80
```

Esses valores são gate experimental, não leis cognitivas.

Eles permanecem no World State e podem ser alterados sem modificar a Memoria.ia.

## Decisão

Cada link recebe uma decisão:

```text
admitted = true/false
rejection_reasons = [...]
```

Possíveis razões incluem:

- `insufficient-repetitions`;
- `insufficient-independent-slices`;
- `insufficient-rho`;
- `insufficient-selectivity`;
- `insufficient-temporal-stability`;
- `insufficient-evidence-score`;
- `insufficient-direction-confidence`.

Nenhum critério isolado transforma uma associação em verdade.

## Candidato admitido

Um candidato contém somente estrutura:

```text
candidate_id
pattern_a
pattern_b
orientation
orientation_confidence
rho
repetitions
selectivity
temporal_stability
evidence_score
mean_dt
variance_dt
supporting_slice_ids
supporting_frame_ids
```

O payload transportável usa apenas endereços opacos:

```text
temporal:pattern:<id>
temporal:pattern:<id>
```

Não inclui:

- Water;
- nome de sensor;
- intensidade;
- fluxo;
- "causa";
- significado em linguagem natural;
- regra semântica.

## Seleção real

Com três episódios independentes da mesma trajetória:

```text
i2(frame 0) -> i1(frame 1)
```

e:

```text
i2(frame 0) -> i0(frame 2)
```

possuem o mesmo número de repetições.

A associação temporalmente mais próxima acumula `rho` maior e atravessa o gate.

A associação mais distante permanece rejeitada por `insufficient-rho`.

Assim o seletor não está simplesmente copiando todas as arestas aprendidas.

## Seletividade

Um teste adversarial cria dois padrões muito frequentes individualmente, mas que
coincidem poucas vezes.

Mesmo com três repetições conjuntas, a baixa seletividade impede admissão.

Isso evita interpretar coincidência entre padrões comuns como relação forte.

## Estabilidade temporal

Outro teste mantém a mesma ordem A→B, mas altera fortemente o deslocamento temporal
entre episódios.

A variância de `dt` reduz a estabilidade temporal e o link é rejeitado.

## Direção

Um teste alterna:

```text
A -> B
B -> A
A -> B
B -> A
```

A direção dominante fica abaixo do limiar e o candidato é rejeitado.

Isso impede converter uma associação temporalmente inconsistente em relação orientada.

## Proveniência

Candidatos admitidos preservam:

- IDs das RealitySlices independentes;
- IDs dos frames sensoriais que deram suporte.

No cenário de três episódios:

```text
3 slices independentes
9 frames de origem
```

A evidência continua auditável.

## Fronteira com Memoria.ia

O Gate exige explicitamente:

```text
TemporalAssociator
      ↓
Evidence Selector
      ↓
TemporalEvidenceCandidate
      X
Memoria.ia
```

A seleção não altera:

- `InterventionConsequenceMemory`;
- regimes situados;
- World State.

O próximo gate deverá definir **como** um candidato estrutural aprovado pode ser
apresentado à Memoria.ia sem fingir causalidade ou semântica.

## Invariantes

- um episódio isolado não é admitido;
- slices independentes são obrigatórias;
- proximidade temporal influencia admissão;
- baixa seletividade rejeita coincidências comuns;
- instabilidade temporal rejeita relações inconsistentes;
- direção inconsistente é rejeitada;
- proveniência é preservada;
- payload admitido é pré-semântico;
- seleção não escreve World State;
- seleção não escreve Memoria.ia;
- resultado é determinístico.

## Próxima evolução

O Life Gate 010 deve introduzir um contrato próprio de **observação estrutural temporal**
na Memoria.ia V2, separado de `InterventionConsequenceMemory`.

Esse contrato deve receber candidatos aprovados como evidência observacional, permitir
reforço/conflito ao longo do tempo e manter proveniência, sem transformar automaticamente
associação temporal em causalidade, fato ou lei.
