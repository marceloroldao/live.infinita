# NPC Compound Strategy 001

## Goal

Allow a need-driven NPC to choose an explicit multi-stage strategy without giving the NPC or an LLM direct mutation authority.

## v1 strategies

- `direct`: go straight to the selected target.
- `via_shelter`: go first to an explicit shelter entity, then continue to the final target.

The wait strategy is intentionally not implemented in v1 because waiting must consume logical ticks without inventing a world mutation. It belongs in the plan scheduler as a temporal step.

## Deterministic policy

The `NpcCompoundStrategyCatalog` is optional. When present:

- if `danger_level < high_risk_threshold`, choose `direct`;
- if `danger_level >= high_risk_threshold` and a valid shelter exists, choose `via_shelter`;
- if no valid shelter exists, fall back to `direct`.

The selection reason and ranked alternatives are stored with the need proposal for auditability.

## Compound intent

`via_shelter` compiles to:

```json
{
  "intent": "move_via_entities",
  "actor_entity_id": "npc",
  "via_entity_ids": ["shelter"],
  "target_entity_id": "home"
}
```

`DeterministicIntentPlanner` expands this compound intent into ordinary `move_to_position` and `move_to_entity` plan steps. Therefore every authoritative movement step continues through the existing `AgentIntentResolver`, `PlanScheduler` and `Mutation Gate`.

## Invariants

1. Strategy selection never mutates the world.
2. Missing intermediate entities fail closed or fall back to direct selection before planning.
3. Compound planning preserves explicit region topology and step revalidation.
4. Every final executable step is an already supported simple intent.
5. Strategy metadata is audit data, not authority.

## Next

Add temporal strategy steps (`wait_ticks`) driven by Simulation Clock, then learn strategy-level reward/cost so `direct`, `via_shelter` and `wait` can be compared from experience rather than only a baseline policy.
