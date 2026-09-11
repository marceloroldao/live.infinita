# MVP-012 — Context Package + stale guard

## Objetivo

Dar ao AI Router contexto suficiente para interpretar uma intenção sem transformar a LLM em autoridade sobre o mundo.

Fluxo:

`World State + Actor State + Binding -> Context Compiler -> AI Router -> proposta pending -> stale guard -> Gateway -> Intent -> Validator -> Runtime`

O Context Package é somente leitura. Ele não é um formato de escrita do World State.

## Context Package v1.0

O compilador gera um pacote determinístico com:

- referência do mundo: `world_id`, `version`, `sequence`, `state_hash`;
- ambiente atual;
- lista limitada de entidades com `id`, `type`, posição, escala e propriedades;
- Actor State relevante, quando existe;
- vínculo ator/personagem e a entidade vinculada, quando existe;
- política explícita: `llm_may_propose_only=true`, `direct_world_write=false`, `commit_requires_validator=true`;
- `context_digest` SHA-256 canônico.

O limite inicial é 64 entidades. O pacote informa `entities_total` e `entities_truncated`.

## Proveniência da proposta

Uma proposta AI persiste somente a referência do contexto, não uma cópia completa do pacote:

- `digest`;
- `schema_version`;
- `world_version`;
- `world_sequence`;
- `world_state_hash`;
- `actor_key` relevante;
- `bound_entity_id` relevante.

Isso permite auditar em qual estado a interpretação foi feita sem duplicar o World State dentro do log de propostas.

## Stale guard

No commit, o runtime compara a referência de mundo da proposta com o estado atual dentro do mesmo `world_lock` usado para o commit.

Se qualquer um destes campos mudou:

- `version`;
- `sequence`;
- `state_hash`;

a proposta não é executada. Ela passa de `pending` para `stale`, o mundo não é alterado e a API retorna HTTP 409.

Isso evita o cenário:

1. LLM interpreta o mundo na versão N;
2. outro evento muda o mundo para N+1;
3. uma decisão antiga é aplicada cegamente sobre N+1.

Uma proposta `stale` precisa ser gerada novamente a partir de um Context Package novo.

## Separação Actor State x saída da LLM

Eventos reentrando como `source=agent` não alimentam Actor State. A saída da LLM pode virar uma ação validada no mundo, mas não vira evidência sobre o usuário.

O backfill também ignora eventos de `source=agent`.

## Endpoint de inspeção

`POST /api/ai/context/preview` usa a mesma identidade de entrada da proposta, mas apenas compila e devolve o contexto.

Exemplo:

```bash
TOKEN=$(sudo sed -n 's/^LIVE_INFINITA_OPERATOR_TOKEN=//p' /etc/live-infinita/operator.env)

curl -s -X POST http://127.0.0.1:8080/api/ai/context/preview \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{
    "text":"o que devo fazer agora?",
    "source":"api",
    "actor_id":"operator",
    "display_name":"Operator"
  }'
```

Critério: `world_mutated=false` e o `context_digest` deve permanecer igual enquanto os mesmos estados de entrada permanecerem iguais.

## Validação A — testes unitários

```bash
python3 -m unittest tests/test_mvp011_ai_router.py -v
python3 -m unittest tests/test_mvp011_ai_proposals.py -v
python3 -m unittest tests/test_mvp012_context_package.py -v
```

## Validação B — proposta com contexto

Registre a baseline:

```bash
curl -s http://127.0.0.1:8080/api/replay/verify
```

Crie uma proposta:

```bash
curl -s -X POST http://127.0.0.1:8080/api/ai/proposals \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"text":"deixe a clareira de dia"}'
```

A proposta deve conter `context.digest`, `context.world_version`, `context.world_sequence` e `context.world_state_hash`, com `world_mutated=false`.

Sem qualquer evento intermediário, o commit deve passar e o replay continuar íntegro.

## Validação C — stale guard

1. crie uma proposta AI e anote o `proposal_id`;
2. **não** faça commit ainda;
3. altere o mundo por outro caminho determinístico, por exemplo:

```bash
curl -s -X POST http://127.0.0.1:8080/api/simulate \
  -H 'Content-Type: application/json' \
  -d '{"action":"toggle_fire"}'
```

4. tente o commit da proposta antiga:

```bash
curl -i -X POST \
  http://127.0.0.1:8080/api/ai/proposals/SEU_PROPOSAL_ID/commit \
  -H "Authorization: Bearer $TOKEN"
```

Resultado esperado:

- HTTP 409;
- `stale_context=true`;
- `world_mutated=false`;
- proposta atual passa a `status=stale`;
- nenhum Event/Delta adicional é criado pela tentativa stale;
- `/api/replay/verify` permanece `ok=true`.

## Critério de congelamento

O MVP-012 pode ser congelado quando:

1. os testes unitários passarem;
2. o Context Package for determinístico;
3. uma proposta válida puder ser criada e commitada normalmente;
4. uma proposta baseada em estado antigo for bloqueada como stale;
5. eventos `agent` não incrementarem Actor State;
6. replay continuar determinístico nos dois cenários.

## Próxima direção

Depois do MVP-012, o Context Compiler poderá ganhar fontes adicionais — principalmente Memoria.ia — sem mudar a regra de autoridade. Memoria.ia entra como estado cognitivo/proveniência relevante; LLM continua operador probabilístico; Validator + Runtime continuam responsáveis pela mutação do mundo.
