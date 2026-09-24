# NPC Composite Strategy 001

## Goal

Let a need-driven NPC compare deterministic multi-phase strategies without giving the decision layer direct mutation authority.

## Candidates

- `direct`: move directly to the final target.
- `via_shelter:<entity_id>`: move to a shelter, then to the final target.
- `wait_then_direct`: wait a fixed number of logical ticks, then move directly.

Each candidate is a pure data object containing semantic phases, predicted satisfaction, estimated route cost, estimated risk, wait cost and expected value.

## Ranking

The initial deterministic score is:

`expected_value = predicted_satisfaction - travel_penalty - risk_penalty - wait_penalty`

The strategy layer never bypasses exploration policy from the need-learning layer. It also does not mutate world state.

## Compilation

`NpcStrategyCompiler` transforms a chosen candidate into `npc_strategy_plan_v1`. Each phase receives the actor id, need, decision context, strategy id and phase index.

Supported phase kinds in v1:

- `move_to_entity`
- `wait_ticks`

Compilation grants no authority. A future composite executor must feed movement phases through the existing Intent Planner and Mutation Gate. Waiting must advance only by logical Simulation Clock ticks and must not use wall-clock sleeps.

## Invariants

1. No strategy candidate or compiled plan can mutate the authoritative world.
2. Unknown phase kinds fail closed.
3. Waiting has an explicit cost and can never be free.
4. Strategy selection is deterministic for the same inputs.
5. The original decision context remains attached to every phase for later outcome learning.
