# Memoria.ia V2 — Shadow Mode

O Shadow Mode é a etapa de validação passiva entre o runtime autônomo da Live.infinita e o contrato cognitivo da Memoria.ia V2.

## Objetivo

Observar decisões reais de Nov sem entregar autoridade de decisão ou escrita à Memoria.ia.

Fluxo:

`World State -> CognitiveFrame -> candidatos -> tick autoritativo normal -> observação do resultado -> shadow metrics`

O tick autoritativo continua sendo executado pelo mesmo single-writer. O shadow é um wrapper externo ao `WorldTickRunner` e não participa de proposal, plan, mutation gate ou commit.

## Invariantes

- `World State` continua sendo a autoridade.
- Shadow nunca chama `commit_action`, mutation gate ou planner.
- Shadow nunca cria proposal ou plan.
- Saída do shadow nunca é gravada como fato do mundo.
- Falha no shadow não bloqueia, repete ou reverte o tick.
- O modo é desativado por padrão.
- O log só é persistido em fronteiras relevantes para evitar I/O a cada tick de 500 ms.

## Ativação

Arquivo do serviço autônomo:

`/etc/live-infinita/autonomous-world.env`

Adicionar ou alterar:

```text
LIVE_INFINITA_MEMORIA_V2_SHADOW=1
```

Depois reiniciar apenas o processo autônomo:

```text
sudo systemctl restart live-infinita-autonomous-world.service
```

Para desligar:

```text
LIVE_INFINITA_MEMORIA_V2_SHADOW=0
```

## Dados

Quando ativo, o processo autônomo grava:

`/var/lib/live-infinita/autonomous-world/memoria-v2-shadow.jsonl`

Cada registro contém:

- `frame_id`
- referência de tick/version antes e depois
- quantidade de candidatos
- melhor candidato estrutural para o resultado observado
- `match_score`
- sinal de ambiguidade
- resumo de atividade do tick
- `authority=shadow-observer`
- `world_mutated_by_shadow=false`

O wrapper não grava ticks comuns. São considerados limites relevantes, entre outros:

- plano concluído/falho/cancelado
- necessidade agendada/concluída/falha
- estratégia relevante
- idle wander agendado/concluído/falho
- evento mundial
- evento condicional

## Métricas

A API protegida por token de operador expõe:

`GET /api/cognitive/v2/shadow/metrics`

Ela retorna somente observabilidade. Não habilita seleção nem escrita.

As métricas atuais medem cobertura estrutural dos candidatos gerados pelo `CognitiveFrame`, incluindo taxa de correspondência exata e ambiguidade.

## Próxima fase

A próxima fase não deve conectar um endpoint de decisão inventado. Primeiro deve existir um contrato real e versionado da Memoria.ia V2 para seleção/ranking de candidatos.

Quando esse contrato existir, a primeira integração deve continuar em shadow:

1. enviar o mesmo `CognitiveFrame`/payload à Memoria.ia V2;
2. registrar qual candidato ela teria selecionado;
3. deixar o runtime autoritativo tomar a decisão real normalmente;
4. comparar seleção prevista, resultado real e custo/latência;
5. somente depois discutir autoridade limitada por policy gate.

Nenhuma promoção para decisão ativa deve ocorrer apenas por taxa de acerto isolada; latência, estabilidade, ambiguidade, proveniência e comportamento sob falha também precisam ser avaliados.
