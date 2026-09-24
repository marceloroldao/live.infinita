# MVP-006 — TikTok Audience Events

## Objetivo

Ampliar a integração real do TikTok para sinais de audiência (`join`, `like`, `gift`) sem permitir que esses eventos alterem o World State diretamente.

## Arquitetura

```text
TikTok LIVE
  ├─ CommentEvent -> /api/source/tiktok/event -> Intent/Validator -> Runtime -> World State
  ├─ JoinEvent ----\
  ├─ LikeEvent -----+-> /api/audience/tiktok/event -> audience-events.jsonl -> WebSocket
  └─ GiftEvent ----/
```

Comentários continuam sendo tratados como possíveis intenções. Eventos de audiência seguem por um side channel persistente e observável.

## Persistência

Os eventos de audiência ficam em:

```text
/var/lib/live-infinita/audience-events.jsonl
```

Eles não incrementam `world.version`, `world.sequence` nem alteram `state_hash`.

## Deduplicação

O runtime considera duplicado o mesmo par `(source, source_event_id)`. Um evento duplicado retorna `duplicate=true` e não é persistido novamente.

## Gifts em streak

O bridge ignora atualizações intermediárias de streak e encaminha somente o fechamento da sequência para evitar múltiplos registros do mesmo envio progressivo.

## Endpoints

- `GET /api/audience/events`
- `POST /api/audience/{source}/event`
- `GET /api/replay/verify`

## Critério de validação

1. health deve mostrar `mvp=006`, `version=0.7.0`, `replay_ok=true`;
2. testes de mapping devem passar;
3. durante LIVE real, observar pelo menos um `join` ou `like` chegando como `audience kind=... http=202`;
4. se houver gift, confirmar metadata do presente e fechamento de streak;
5. `GET /api/audience/events` deve listar os sinais recebidos;
6. `GET /api/replay/verify` deve continuar `ok=true` e com o mesmo hash antes/depois de eventos de audiência puros.
