# MVP-011 — AI Router controlado

## Objetivo

Introduzir uma LLM como camada probabilística de interpretação sem entregar autoridade sobre o World State.

Fluxo proposto:

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

Depois reentra no Gateway e precisa passar novamente por Intent e Validator.

## Fase A — core isolado

Esta primeira entrega adiciona `apps/ai/router.py` e testes unitários com transporte injetável. A integração HTTP/persistência de propostas vem na próxima alteração do mesmo MVP.

Critérios da Fase A:

1. ação permitida é normalizada;
2. ação fora da allowlist não é acionável;
3. `none` permanece não acionável;
4. confiança é limitada a `[0,1]`;
5. JSON inválido falha fechado;
6. texto vazio é rejeitado;
7. nenhuma chamada ao World Runtime existe dentro do módulo.

## Fase B — proposal store e API

Próxima etapa:

- `POST /api/ai/proposals` protegido pela chave de operador no primeiro MVP;
- persistência append-only em `ai-proposals.jsonl`;
- `GET /api/ai/proposals` com fold pelo `proposal_id`;
- `POST /api/ai/proposals/{id}/commit`;
- commit traduz ação para texto canônico e chama o pipeline existente;
- replay antes/depois precisa continuar consistente.

## Política inicial

- OpenAI key/model vêm do IntegrationStore do MVP-010.
- Nenhuma saída da LLM é gravada automaticamente como fato do mundo.
- Nenhuma resposta textual da LLM entra em Actor State como evidência do usuário.
- O modelo é operador probabilístico, não autoridade.
- Godot permanece fora do caminho crítico deste MVP.
