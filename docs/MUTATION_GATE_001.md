# Mutation Gate 001

A Mutation Gate is the deterministic policy boundary between mutation proposals and the authoritative cold-backed world.

## Separation of responsibilities

- `MutationGate`: decides whether a principal is allowed to request the canonical operations.
- `GuardedMutationService`: commits only accepted decisions and injects provenance.
- `ColdEntityMutator`: applies accepted entity mutations.
- `ColdAuthoritativeWorldEngine`: records event/delta/hash-chain state.

Rejected proposals never write the cold store and never create an event, delta, world version or state hash.

## Principal

A principal carries:

- `source`
- `actor_id`
- `authority`
- optional `subject_entity_id`

## Authority v1

| Authority | Allowed direct mutations |
|---|---|
| `system` | all canonical operations |
| `operator` | all canonical operations |
| `world_agent` | create, set, move, link, unlink |
| `entity_agent` | set, move, link, unlink only on its `subject_entity_id` |
| `audience` / `observer` / unknown | none |

`world_agent` deliberately cannot `remove` entities or `set_world` directly in v1. Those operations require operator/system authority.

## Provenance

Every accepted guarded commit adds `event.context.mutation_provenance`:

```json
{
  "source": "agent",
  "actor_id": "nov-agent",
  "authority": "entity_agent",
  "subject_entity_id": "nov",
  "policy": "mutation_gate_v1",
  "decision": "accepted"
}
```

This makes authority and causal origin part of the append-only event history and therefore part of the deterministic delta hash chain.

## Security invariant

AI, audience, external source adapters and future Memoria.ia integrations should propose mutations through the Gate. They must not receive a direct reference to `ColdEntityMutator` or unrestricted `commit_operations()`.

Trusted internal/bootstrap code may still use the lower-level APIs during migration and deterministic replay tooling.
