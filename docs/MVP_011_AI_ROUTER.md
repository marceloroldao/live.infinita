# MVP-011 — AI Router controlado

## Objetivo

Introduzir uma LLM como camada probabilística de interpretação sem entregar autoridade sobre o World State.

Fluxo implementado:

`texto livre -> AI Router -> proposta estruturada -> pending -> commit explícito -> Gateway -> Intent -> Validator -> Runtime determinístico`

A LLM nunca chama `engine.commit_action`, nunca grava World State e nunca escreve Event/Delta diretamente.

## Contrato do AI Router

A saída permitida é um objeto lógico com:

- `action`: `spawn_person`, `move_tree`, `toggle_fire`, `set_night`, `set_day`, `reset` ou `none`;
- `confidence`: número entre 0 e 1;
- `reason`: justificativa curta.

Qualquer ação fora da allowlist é convertida para proposta não acionável.

## Reentrada determinística

Uma proposta aprovada não é enviada diretamente ao Runtime. Ela é convertida para texto canônico já reconhecido pelo Intent Engine:

- `spawn_person` -> `+ visitante`
- `move_tree` -> `mover árvore`
- `toggle_fire` -> `fogueira`
- `set_night` -> `noite`
- `set_day` -> `dia`
- `reset` -> `reset`

Depois reentra no Gateway e precisa passar novamente por Intent e Validator. A reentrada usa `source=agent` e preserva no metadata o `ai_proposal_id`, modelo, confiança e fonte original.

## Fase A — core isolado

`apps/ai/router.py` contém o boundary da LLM e usa transporte injetável nos testes. O módulo não importa nem acessa o World Runtime.

Critérios da Fase A:

1. ação permitida é normalizada;
2. ação fora da allowlist não é acionável;
3. `none` permanece não acionável;
4. confiança é limitada a `[0,1]`;
5. JSON inválido falha fechado;
6. texto vazio é rejeitado;
7. nenhuma chamada ao World Runtime existe dentro do módulo.

## Fase B — proposal store e API

Implementado:

- `apps/ai/proposals.py` com log append-only em `/var/lib/live-infinita/ai-proposals.jsonl`;
- leitura atual faz fold por `proposal_id`, preservando o histórico bruto;
- estados `pending`, `non_actionable`, `committed` e `rejected`;
- limiar inicial `AI_MIN_CONFIDENCE = 0.75` para permitir estado `pending`;
- `POST /api/ai/proposals` protegido pela chave de operador;
- `GET /api/ai/proposals` protegido;
- `POST /api/ai/proposals/{id}/commit` protegido;
- `POST /api/ai/proposals/{id}/reject` protegido;
- geração de proposta retorna `world_mutated=false` e não toca Event/Delta;
- commit explícito reentra no Gateway com texto canônico;
- somente depois de Gateway -> Intent -> Validator o Runtime pode gerar Event/Delta;
- o health do MVP-011 expõe contadores do AI Router e `direct_world_write=false`.

## Política inicial

- OpenAI key/model vêm do IntegrationStore do MVP-010.
- Toda chamada à OpenAI para gerar proposta exige autenticação do operador neste MVP.
- Uma proposta com confiança abaixo de `0.75` permanece registrada, mas como `non_actionable`.
- Nenhuma saída da LLM é gravada automaticamente como fato do mundo.
- Nenhuma resposta textual da LLM entra em Actor State como evidência do usuário.
- O modelo é operador probabilístico, não autoridade.
- Godot permanece fora do caminho crítico deste MVP.

## Testes unitários

```bash
python3 -m unittest tests/test_mvp011_ai_router.py -v
python3 -m unittest tests/test_mvp011_ai_proposals.py -v
```

O primeiro conjunto valida parsing/allowlist/fail-closed do AI Router. O segundo valida persistência append-only, fold de estado e os ciclos pending -> committed/rejected sem World Runtime.

## Validação na VM

Depois de instalar a branch e configurar a OpenAI em `/manage/`:

1. capturar baseline:

```bash
curl http://127.0.0.1:8080/api/replay/verify
curl http://127.0.0.1:8080/api/world
```

2. criar uma proposta com a chave do operador:

```bash
curl -X POST http://127.0.0.1:8080/api/ai/proposals \
  -H "Authorization: Bearer $LIVE_INFINITA_OPERATOR_TOKEN" \
  -H 'content-type: application/json' \
  -d '{"text":"deixe a clareira de noite","source":"api","actor_id":"operator"}'
```

3. antes do commit, confirmar que `version`, `sequence`, `state_hash`, events e deltas não mudaram;
4. consultar `GET /api/ai/proposals` e capturar o `proposal_id` pending;
5. fazer commit explícito:

```bash
curl -X POST http://127.0.0.1:8080/api/ai/proposals/PROPOSAL_ID/commit \
  -H "Authorization: Bearer $LIVE_INFINITA_OPERATOR_TOKEN"
```

6. confirmar que o evento produzido tem `source=agent` e metadata com `ai_proposal_id`;
7. confirmar `/api/replay/verify` com `ok=true` e `current_hash == replay_hash`.

## Critério de congelamento do MVP-011

O MVP só deve ser congelado depois que a VM provar as duas propriedades ao mesmo tempo:

1. proposta da LLM sozinha não altera o mundo;
2. proposta explicitamente aprovada só altera o mundo depois de passar pelo pipeline determinístico existente.
