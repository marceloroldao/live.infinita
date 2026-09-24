# Conditional Plan Effects 001

## Goal

Allow deterministic world conditions to create semantic agent plans instead of only applying immediate mutations.

Example:

`Nov remains in the village for 20 logical ticks -> NPC receives goal: approach Nov`

The trigger schedules a plan. It does not teleport the NPC and does not mutate the world at scheduling time.

## Lifecycle

1. ConditionalEventScheduler evaluates a typed condition.
2. The condition crosses its configured trigger boundary.
3. ConditionalPlanDispatcher creates an `agent_intent` record in ProposalLedger.
4. The proposal is marked `approved` by the pre-authorized conditional policy that owns the trigger.
5. PlanScheduler creates a persistent plan linked to that proposal.
6. Future world ticks execute at most one plan step per tick.
7. Every plan step resolves to canonical operations and passes MutationGate.
8. When the plan completes, ProposalLedger moves from `approved` to `committed` using the final real `mutation_decision_id` and `world_event_id`.
9. If execution is rejected or becomes invalid, the proposal is rejected rather than falsely marked committed.

## Security boundary

A conditional trigger gains no new mutation authority.

The principal persisted on the conditional rule is copied into the plan. Therefore an `entity_agent` can still mutate only its own subject entity. A trigger cannot use plan creation to make an NPC modify another entity directly.

Plan creation itself is non-authoritative: it changes planning ledgers, not world state.

## Effect kinds

### mutation

Existing behavior. The condition fires canonical operations through GuardedMutationService immediately in that logical tick.

### plan_intent

The condition fires a semantic intent such as:

```json
{
  "intent": "move_to_entity",
  "actor_entity_id": "npc_01",
  "target_entity_id": "nov"
}
```

The effect creates ProposalLedger + PlanLedger records. It does not call the world engine directly.

## Idempotency

Each firing uses a deterministic key based on:

`conditional_event_id + fire_index`

Repeating the same dispatch cannot duplicate the proposal or plan.

## Provenance

The conditional event stores the most recent:

- `last_proposal_id`
- `last_plan_id`
- `last_fired_tick`
- `fire_count`

The proposal stores the trigger origin and metadata. The plan stores the proposal ID. Authoritative execution later supplies mutation decision and world event linkage.

## Example

Condition:

```json
{
  "kind": "entity_in_region",
  "entity_id": "nov",
  "region_id": "village",
  "sustain_ticks": 20
}
```

Effect:

```json
{
  "intent": "move_to_entity",
  "actor_entity_id": "npc_01",
  "target_entity_id": "nov"
}
```

Result:

`condition true for 20 ticks -> approved semantic proposal -> persistent NPC plan -> one guarded movement step per world tick`

## Non-goals

This version does not let arbitrary untrusted users register pre-authorized conditional rules. Rule registration remains an operator/system policy concern.
