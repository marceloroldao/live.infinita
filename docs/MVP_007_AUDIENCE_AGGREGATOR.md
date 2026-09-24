# MVP-007 — Audience Aggregator + Proposal Gate

## Objetivo
Transformar telemetria de audiência em propostas auditáveis sem conceder autoridade direta ao público sobre o World State.

## Fluxo

```text
TikTok join/like/gift
        ↓
audience side channel
        ↓
Audience Aggregator
        ↓
Pending Proposal
        ↓
explicit commit endpoint
        ↓
Intent → Validator → Runtime
        ↓
Event/Delta → World State
```

## Regras iniciais
- 10 joins em 30 s → proposta `spawn_person`
- 50 likes em 30 s → proposta `toggle_fire`
- 1 gift finalizado → proposta `spawn_person`

As regras são deliberadamente simples e servem apenas para validar arquitetura.

## Segurança arquitetural
Atingir um limiar não altera `world.version`, `sequence` ou `state_hash`. O Aggregator grava uma proposta `pending` em `/var/lib/live-infinita/audience-proposals.jsonl`. A mudança só ocorre após `POST /api/audience/proposals/{proposal_id}/commit`, que converte a proposta em entrada normal do Gateway e a submete ao Intent/Validator antes do Runtime.

## Endpoints
- `GET /api/audience/rules`
- `GET /api/audience/proposals`
- `POST /api/audience/proposals/{proposal_id}/commit`
- `POST /api/audience/{source}/event`

## Validação
1. confirmar health `mvp=007`, `version=0.8.0`, `replay_ok=true`;
2. executar `python3 -m unittest tests/test_mvp007_audience_aggregator.py -v`;
3. enviar 10 joins simulados em menos de 30 s;
4. confirmar uma proposta `pending` e nenhuma alteração no hash do mundo;
5. fazer commit explícito da proposta;
6. confirmar novo Event/Delta e replay `ok=true`.
