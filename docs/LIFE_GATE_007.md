# Life Gate 007 — Synchronized Multimodal Perception

## Objetivo

Evoluir a percepção da Nov de um único canal quantitativo para um quadro sensorial
sincronizado com múltiplos canais independentes.

O gate não cria um conceito composto. Cada canal continua separado até a Memoria.ia.
A combinação só existe porque os sinais coexistem no mesmo instante cognitivo.

## Canais

O cenário usa quatro canais independentes:

```text
s_presence   -> presença/ausência
s_intensity  -> faixa de intensidade
s_trend      -> tendência temporal
s_flow       -> transferência dominante observada
```

Os valores entregues à cognição são IDs opacos:

```text
p0 / p1
i0 / i1 / i2
t0 / t1 / t2
d0 / d1 / d2 / ...
```

A Memoria.ia não recebe o significado desses símbolos.

## Frame sincronizado

`environmental_multisensor_runtime.py` amostra todos os canais no mesmo tick e cria um
único:

```text
sensor_frame_id
```

Cada leitura carrega o mesmo frame ID no World State e no Event/Delta da amostragem.

A projeção cognitiva continua usando entidades independentes por canal. Não existe um
endereço `multimodal_context` nem um nódulo sintético “água descendo”, “água fluindo”
ou equivalente.

## Trajetória do Gate

### Frame 0

Antes do fluxo distribuído:

```text
presence  = p1
intensity = i2
trend     = t0
flow      = d0
```

Nov observa duas vezes e estabelece o primeiro regime situado.

### Frame 1

Após o primeiro tick físico:

```text
spring water: 100 -> 20

presence  = p1
intensity = i1
trend     = t2
flow      = d1
```

O novo conjunto de símbolos produz outro contexto situado.

O regime do Frame 0 não é reutilizado. A curiosidade volta a selecionar `probe`.
Depois de duas observações, o Frame 1 consolida seu próprio regime.

### Frame 2

Após o segundo tick físico:

```text
spring water: 20 -> 10

presence  = p1
intensity = i0
trend     = t2
flow      = d0
```

Parte dos sinais permanece igual e parte muda.

Mesmo assim, a configuração estrutural completa é diferente:

```text
context(Frame 2) != context(Frame 1) != context(Frame 0)
```

A Memoria.ia não recebe nenhuma regra dizendo que intensidade, tendência e fluxo estão
relacionados.

## Tendência temporal

O canal `s_trend` compara a quantidade local atual com a amostra anterior do próprio
canal.

Ele possui uma pequena deadband para evitar tratar variações mínimas como mudança
estrutural.

A primeira amostra não possui histórico e portanto gera o símbolo estável inicial.

## Direção/transferência

O canal `s_flow` consulta o último balanço ambiental distribuído da região observada.

Quando múltiplos fluxos saem da região, o canal escolhe a transferência dominante por
quantidade, com desempate determinístico por route ID.

O mapeamento route→símbolo pertence à configuração sensorial do World State. A
Memoria.ia recebe apenas o símbolo final.

## Independência dos canais

O teste exige que o estado cognitivo contenha quatro relações sensoriais e quatro
entidades de leitura independentes.

Não é permitido gerar no runtime um símbolo composto como:

```text
high_water_falling_toward_channel
```

O eventual reforço entre sinais deve surgir posteriormente pela trajetória e
recorrência temporal.

## Fronteira cognitiva

Continuam ocultos:

- quantidade exata;
- `by_region`;
- `initial_total`;
- `evaporated_total`;
- `raw_value`;
- `source_value`;
- regras físicas;
- significado semântico dos canais.

Apenas IDs estruturais de leitura entram em `state_addresses`.

## Invariantes

- todos os canais do frame usam o mesmo tick/frame ID;
- canais permanecem estruturalmente independentes;
- física e amostragem não escrevem Memoria.ia;
- nenhuma regra semântica composta é criada;
- contexto muda quando a configuração observável muda;
- regime situado não vaza entre configurações diferentes;
- estrutura histórica ainda pode transferir ambiguidade;
- replay é determinístico;
- Gates 001–006 permanecem compatíveis.

## Próxima evolução

O Life Gate 008 pode introduzir uma janela temporal de frames sensoriais e gerar
`RealitySlice` a partir da sequência multimodal, permitindo testar reforço por
proximidade temporal, recorrência e direção temporal antes de enviar estruturas
consolidadas à Memoria.ia.
