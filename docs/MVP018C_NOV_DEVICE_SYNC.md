# MVP-018C — transporte observacional de Nov por dispositivo (preparado, desligado)

Arquitetura: `npc-episodes.jsonl` (somente leitura) → prévia tipada
`live-infinita-npc-episode-observation/v1` → cliente one-shot em processo separado
→ Memoria.ia Server com autenticação Ed25519 → núcleo Memoria.ia V2 EvidenceCore.

Este código **não é iniciado pela Live**, não altera o World State, não fornece
respostas à cognição de Nov e não faz sincronização automaticamente.
O Godot, API, narrador e Single Writer permanecem independentes.

## Contratos presentes nos repositórios

- Live.infinita: `packages/observability/nov_episode_sync.py` gera envelope com
  `record_key`, `content_sha256` e fonte `need_outcome` validada.
- Memoria.ia V2: `POST /api/v1/external/episodes`, chave interna `X-Memoria-Key`
  mantida somente no Memoria.ia Server; evidência com persistência durável.
- Memoria.ia Server: `POST /api/server/v1/device/observations/npc-episodes`,
  autenticação `Authorization: Device <token>` por desafio Ed25519, escopos
  `memory.sync` e `world.connect`, tipo server e grupo aprovado
  `live-world:<world_id>`.
- Recibo `memoria-server-npc-episode-receipt/v1`: `stored` ou `duplicate`,
  identidade da fonte, hash, servidor, dispositivo, namespace e persistência.

## Segurança do cliente

O worker `packages/observability/nov_episode_delivery.py` e CLI
`apps/nov-sync/nov_sync_main.py` possuem execução explícita one-shot, no máximo
16 registros processados por comando. Nenhum serviço ou timer é registrado.
Por padrão, a variável `LIVE_INFINITA_NOV_SYNC_ENABLED` não está ativa.

O servidor remoto deve usar HTTPS (somente loopback de teste aceita HTTP).
O cliente fixa `server_id` e `device_id`, confere a mensagem antes de assinar
o desafio e valida todos os campos críticos do recibo, inclusive persistência
durável. Um timeout pode ocasionar reenvio, mas a identidade imutável torna
o episódio idempotente. HTTP 409, resposta alterada, token inválido, perda do
servidor ou corrupção local não avançam o cursor.

O checkpoint de offset é separado do World State, criado com permissão 0600 e
atualizado atomicamente **após o ACK validado**. A posição local é conferida
com o inode, servidor/dispositivo aprovados e um hash de âncora. Rotação, truncamento ou mudança da fonte
param o envio até reconciliação. Entradas descartadas por serem de outro NPC
não geram ACK; apenas seu offset pode avançar como registro filtrado.

### Pré-requisitos de implantação — não executar prematuramente

1. Instalar as versões adequadas da Memoria.ia V2 e do Memoria.ia Server,
   confirmar a rota central e a identidade do servidor.
2. Inscrever explicitamente a VM da Live como dispositivo Ed25519 `type=server`,
   aprovar `memory.sync`, `world.connect` e grupo `live-world:nov-live-autonomous-001`.
   A chave privada deve permanecer no host cliente, em PEM Ed25519, modo 0600.
3. Instalar `cryptography` em um ambiente isolado para o worker, **não** no
   processo autoritativo por dependência incidental.
4. Configurar, em ambiente protegido do worker, os valores:

   `LIVE_INFINITA_NOV_SYNC_ENABLED=1`
   `LIVE_INFINITA_NOV_SYNC_SERVER_URL=https://...`
   `LIVE_INFINITA_NOV_SYNC_SERVER_ID=<id fixado>`
   `LIVE_INFINITA_NOV_SYNC_DEVICE_ID=<id aprovado>`
   `LIVE_INFINITA_NOV_SYNC_PRIVATE_KEY=<caminho absoluto da chave privada>`
   `LIVE_INFINITA_NOV_SYNC_WORLD_DIR=/var/lib/live-infinita/autonomous-world`
   `LIVE_INFINITA_NOV_SYNC_CHECKPOINT=<caminho fora do mundo autoritativo>`

5. Só após os pré-requisitos, um operador pode testar uma única entrega com
   `python apps/nov-sync/nov_sync_main.py --once --max-records 1`, a partir
   da raiz do repositório com `PYTHONPATH` correto.

Não existe configuração automática de credenciais, serviço de sistema ou
backfill silencioso. A política inicial de histórico e consentimento para
importar os episódios antigos deve ser decidida antes de ativar a ponte.
