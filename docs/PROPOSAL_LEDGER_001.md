# Proposal Ledger 001

## Objective

Unify AI, audience, Memoria.ia and future agent proposals without mixing proposal history with authoritative world replay.

## Lifecycle

```text
proposed -> approved -> committed
proposed -> rejected
proposed -> expired
approved -> rejected
approved -> expired
```

Terminal states are `committed`, `rejected`, and `expired`.

A proposal can only become `committed` when it contains both:

- `mutation_decision_id`
- `world_event_id`

This creates an explicit chain:

```text
proposal_id
  -> mutation_decision_id
     -> world_event_id
        -> authoritative delta/replay
```

## Compatibility migration

The spatial runtime currently uses dual-write:

- existing `ai-proposals.jsonl` remains supported;
- existing `audience-proposals.jsonl` remains supported;
- new `proposal-ledger.jsonl` mirrors actionable proposals;
- source records are linked through `source_proposal_id`;
- idempotency keys prevent duplicate mirroring.

The legacy stores can therefore be removed later without changing the canonical ledger contract.

## Approval boundary

Audience input is proposal-only.

Direct TikTok/YouTube input does not receive mutation authority. The legacy audience proposal commit endpoint is treated as an operator approval endpoint and requires the configured operator bearer token before the runtime marks the proposal as operator-approved.

AI proposals follow the existing operator-protected commit endpoint and are mirrored into the same ledger.

## Separation of histories

`proposal-ledger.jsonl` records lifecycle and intent.

`mutation-decisions.jsonl` records policy decisions, including rejected attempts.

`events.jsonl` and `deltas.jsonl` contain only authoritative world history.

Rejected/expired proposals never become world events.
