# MVP-018B — Contrato tipado de observações de Nov (prévia, sem transporte)

## Estado confirmado nos repositórios

- A Live já persiste resultados reais em `npc-episodes.jsonl`, com `episode_schema=npc_episode_v1`, `source.kind=need_outcome`, ID `plan:<plan_id>`, contexto e resultado quantitativo. Nov/World State continuam sob um único processo escritor.
- O `memoria.ia.server` expõe autenticação Ed25519 por dispositivo e o escopo `memory.sync`, mas a rota de memória **atual** para dispositivos `/api/server/v1/device/memory/structural/observe` aceita apenas `text`, `sequence` e `session_id`.
- O núcleo `memoria.ia` expõe `/api/v1/episodes` com `role=user|assistant` e `text` obrigatório. Converter uma experiência estruturada de Nov em fala sintética alteraria sua proveniência; não usar.

## Contrato da Live, implementado

`GET /api/manage/nov/sync/preview?cursor=0` exige token de operador e devolve `live-infinita-npc-episode-preview/v1`. É uma consulta de **prévia**, não um endpoint de sincronização. A página Vida de Nov tem um botão explícito para gerar a primeira janela local.

Cada envelope (`live-infinita-npc-episode-observation/v1`) contém:

- `record_key`: SHA-256 estável da identidade canônica `{system, world_id, entity_id, episode_id}`;
- `source`: `live.infinita`, ID do mundo, Nov, episódio, esquema, `source_kind=need_outcome`, plano, proposta, revisão;
- `observation`: tick lógico, necessidade, destino, estratégia, contexto tipado e resultado numérico observado;
- `content_sha256`: SHA-256 do envelope canônico sem o próprio digest. Mesma identidade com conteúdo diferente é um conflito, nunca sobrescrita silenciosa;
- `authority=observed-outcome-only` e `world_write_authority=false`.

Entradas com origem incompleta, campos de conversação/narração misturados ou IDs inconsistentes são rejeitadas. Campos livres de `source`, texto de audiência, chave, token e comentários não são exportados. Registros de outro NPC ou outro esquema não são transformados em experiências de Nov.

## Leitura e continuidade

- Janela de no máximo 256 KiB e 16 envelopes por chamada; padrão: 8.
- `input_cursor` e `candidate_next_cursor` são **offsets em bytes**, sempre em fronteiras completas de linha. Um fragmento final sem `\n` fica pendente e nunca é confirmado como registro.
- `ledger_identity` identifica dispositivo/inode da fonte para detectar eventual substituição; `world_id` é lido somente do World State local, não informado pelo navegador.
- Corrupção, cursor fora da faixa, linha longa demais e conflito de chave retornam erro sem avançar cursor.
- `candidate_cursor_is_ack=false`, `central_receipt=null`, `transport_enabled=false`: nenhuma leitura de prévia pode representar confirmação central ou atualizar posição durável.

## Receptor proposto, **ainda não existente** na Memoria.ia Server

Um contrato novo e versionado deve ser implementado no repositório `memoria.ia.server` antes do envio:

`POST /api/server/v1/device/observations/npc-episodes`

- `Authorization: Device <token>` obtido por desafio Ed25519 e certificado ativo, com escopo `memory.sync`; avaliar também `world.connect` no onboarding deste tipo de dispositivo.
- A propriedade/namespace da hierarquia deve ser derivada pelo servidor do dispositivo autenticado. Cliente não escolhe `hierarchy_id`, `source_id`, `organization_id` ou `device_id`.
- O receptor armazena observação tipada separada de chat, previsões e dados factuais; não transforma o resultado em declaração de usuário, não concede autoridade sobre o mundo.
- Após persistência durável, devolve recibo versionado `memoria-server-npc-episode-receipt/v1`, incluindo `record_key`, `content_sha256`, namespace e status `stored` ou `duplicate`.
- Se uma chave já existe com digest divergente: HTTP 409; jamais resolver conflito por timestamp mais novo. Sem recibo durável, não confirmar offset nem eliminar a observação local.
- Reenvio após timeout é permitido por idempotência; a camada cliente só grava checkpoint após verificar recibo, chave, digest, namespace e identidade do servidor. Rotação/truncamento do ledger deve parar o processo até reconciliação.

Esta etapa **não** altera Memoria.ia, não ativa servidor, não envia dados nem cria um recibo fictício. A próxima etapa técnica é construir e testar o receptor tipado no repositório do Server, com identidade e permissões reais, antes do cliente de envio.
