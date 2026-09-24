# MVP-004 — Universal Event Envelope

Objetivo: provar que múltiplas fontes entram no Live Infinita por um contrato único antes do Intent Engine e do runtime determinístico.

## Pipeline

```text
Simulator / API / TikTok / YouTube / Agent
                |
                v
          Source Adapter
                |
                v
     UniversalEventEnvelope v1.0
                |
                v
          Intent Engine
                |
                v
          Rule Validator
                |
                v
     Deterministic World Runtime
                |
                v
        Event + Delta + Hash
```

## UniversalEventEnvelope v1.0

Campos mínimos:

- `envelope_version`
- `source`
- `source_event_id`
- `actor.actor_id`
- `actor.display_name`
- `kind`
- `text`
- `metadata`

O envelope representa proveniência e conteúdo de entrada. O runtime não precisa conhecer SDKs ou formatos específicos de TikTok, YouTube ou outras redes.

## Fontes simuladas no MVP-004

- `simulator`
- `api`
- `tiktok`
- `youtube`
- `agent`

Nesta etapa, TikTok e YouTube são apenas adaptadores de contrato; ainda não existe conexão com APIs externas.

## Endpoints

Endpoint universal:

```text
POST /api/gateway/event
```

Endpoint por fonte:

```text
POST /api/source/{source}/event
```

Exemplo TikTok simulado:

```bash
curl -X POST http://127.0.0.1:8080/api/source/tiktok/event \
  -H 'content-type: application/json' \
  -d '{
    "source_event_id":"tt-001",
    "actor_id":"user-42",
    "display_name":"Visitante TikTok",
    "text":"noite",
    "metadata":{"room":"demo"}
  }'
```

Exemplo YouTube simulado:

```bash
curl -X POST http://127.0.0.1:8080/api/source/youtube/event \
  -H 'content-type: application/json' \
  -d '{
    "source_event_id":"yt-001",
    "actor_id":"user-77",
    "display_name":"Visitante YouTube",
    "text":"dia",
    "metadata":{"channel":"demo"}
  }'
```

## Critérios de validação

1. Health retorna `mvp=004`, `version=0.5.0` e `replay_ok=true`.
2. Teste unitário prova que as cinco fontes geram o mesmo contrato interno.
3. A mesma frase enviada por fontes diferentes produz a mesma Proposed Action.
4. Fonte não suportada é rejeitada antes do runtime.
5. Eventos aceitos preservam `source`, `source_event_id` e identidade do ator na proveniência.
6. Depois de eventos de fontes diferentes, `/api/replay/verify` continua com `ok=true`.

## Teste automatizado

```bash
python3 -m unittest tests/test_mvp004_multi_source.py -v
```

## Princípio arquitetural

Adaptadores conhecem o mundo externo. O Gateway conhece o envelope. O Intent Engine conhece linguagem/intenção. O Validator conhece política. O runtime conhece apenas ações determinísticas validadas.
