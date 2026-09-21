# Memoria.ia V2 Cognitive Gym — Live.Infinita

## Objetivo

Usar a Live.Infinita como ambiente experimental para a Memoria.ia V2 sem acoplar o núcleo cognitivo ao Godot, ao renderer ou a semântica de domínio.

A Live.Infinita continua dona do mundo, das ações válidas, dos deltas e das observações. A Memoria.ia V2 recebe somente endereços estáveis e produz hipóteses, previsões e intenções de experimento.

## Fronteira de responsabilidade

Live.Infinita:
- mantém `World State`, versões, deltas, eventos e `entity_id` estáveis;
- declara quais intervenções são válidas no tick atual;
- executa a intervenção escolhida;
- devolve a observação/consequência real;
- nunca aceita uma ação inventada fora do conjunto permitido.

Memoria.ia V2:
- transforma o frame em estado cognitivo por endereços;
- mantém memória histórica e regimes/contextos ativos;
- resolve ramos concorrentes;
- prevê consequências estruturais;
- detecta surpresa/exhaustion;
- escolhe apenas entre intervenções oferecidas pela Live.Infinita;
- atualiza evidência observacional e intervencional;
- não modifica diretamente o World State.

## Ciclo mínimo

```text
World(t)
  ↓
CognitiveFrame(t)
  ↓
Memoria.ia V2
  ↓
hipóteses / previsão / curiosidade
  ↓
intervenção escolhida entre as disponíveis
  ↓
ProposedAction validada pela Live.Infinita
  ↓
World Runtime aplica Delta(t)
  ↓
WorldEvent + World(t+1)
  ↓
novo CognitiveFrame
  ↓
correção / recovery / atualização de evidência
```

## Contrato de frame

Schema experimental:

`schemas/memoria-v2-cognitive-frame.schema.json`

Campos principais:
- `frame_id`: identidade determinística do frame;
- `tick_id`: relógio lógico do mundo;
- `observer_id`: agente/observador cognitivo;
- `state_addresses`: endereços estáveis do estado observável local;
- `available_interventions`: somente ações que o mundo aceita neste tick;
- `candidate_outcomes`: candidatos concretos que podem ser usados por resolvers estruturais quando disponíveis;
- `provenance`: versão do mundo, snapshot e eventos de origem.

## Regras de segurança arquitetural

1. Memoria.ia V2 nunca cria `entity_id`, `proposal_id` ou ação válida por conta própria.
2. A escolha cognitiva só pode apontar para uma intervenção presente em `available_interventions`.
3. Dois eventos do mesmo tick não recebem ordem causal artificial.
4. O resultado de um tick só entra na memória depois da previsão daquele tick.
5. `exhausted` significa apenas que nenhuma hipótese ativa explicou a observação; não significa falsidade histórica.
6. Histórico e estado cognitivo atual permanecem separados.
7. A mesma memória histórica pode servir vários agentes, mas regimes locais permanecem separados por agente/contexto.
8. Causalidade persistente exige recorrência independente e controles; correlação temporal isolada não basta.

## Primeiro cenário real

Ambiente mínimo:
- 1 agente;
- 2 regiões estruturais;
- 1 fonte ambiental persistente;
- 2 intervenções válidas;
- 2 consequências observáveis;
- mudança de regularidade no meio da execução.

Exemplo conceitual, sem semântica no núcleo:

```text
região R1:
  ação A → efeito X

região R2:
  ação A → efeito Y
```

A Memoria.ia V2 deve demonstrar:
- separação de regimes por contexto;
- previsão antes da observação;
- surpresa quando a regularidade muda;
- recovery sem criar ligação persistente falsa;
- retorno ao regime anterior quando o contexto volta;
- seleção de experimento quando duas hipóteses continuam compatíveis.

## Gate para integração de runtime

Antes de usar uma transmissão real, exigir:
- loop ativo V2 com CI verde;
- frame validável pelo schema;
- conversão determinística World State → addresses;
- nenhuma mutação direta da memória sobre o World State;
- logs por tick com previsão, observação, erro, atenção, regime e evidência;
- replay determinístico a partir de snapshot + eventos;
- nenhuma dependência da OFF.IA.

## Status

Esta integração é experimental. Não deve alterar o `main` até o cenário mínimo ter sido reproduzido de forma determinística e comparado com execução sem Memoria.ia V2.
