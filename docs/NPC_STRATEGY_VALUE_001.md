# NPC Strategy Value 001

## Goal

Choose among already-valid need targets using deterministic expected value without changing authoritative planning or learned evidence.

## Formula

For a target candidate:

`expected_value = predicted_satisfaction - travel_penalty - risk_penalty`

where:

- `predicted_satisfaction` comes from `NpcNeedLearning` global/contextual evidence;
- `travel_penalty = travel_weight * normalized_route_hops`;
- `risk_penalty = risk_weight * max(context danger, target risk)`.

Defaults:

- `travel_weight = 0.12`
- `risk_weight = 0.35`
- `route_hops_scale = 8`

All values are deterministic and auditable.

## Exploration rule

Exploration remains a stronger policy boundary than exploitation. Under-sampled targets stay in the exploration group even if their current expected value is lower. Expected value ranks candidates inside the same exploration/exploitation group.

This prevents an early good result from permanently blocking discovery of alternatives.

## Separation of concerns

`NpcNeedLearning` learns observed satisfaction only.

`NpcStrategyValue` computes decision-time cost/risk overlays.

`DeterministicIntentPlanner` remains authoritative for producing the actual route after a target is selected.

The value layer never mutates world state and never grants authority.

## Scale

Travel cost uses region topology (`RegionCatalog.route`) and does not require loading the full world into RAM. Target risk is read only for explicit candidate targets.

## Compatibility

The strategy layer is opt-in through `NpcNeedScheduler(strategy_provider=...)`. Without a strategy provider, previous target-selection behavior remains unchanged.
