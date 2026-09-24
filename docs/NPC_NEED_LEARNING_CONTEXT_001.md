# NPC Need Learning Context 001

This revision extends deterministic NPC need learning from a global target score to contextual evidence.

## Context

The decision-time context is captured in the semantic intent and follows the plan through completion:

- `period`
- `weather`
- `danger_level` bucketed as `low`, `medium`, or `high`
- `region_id`

The context is canonicalized before it becomes part of a learning key. Coarse danger buckets prevent state explosion from tiny numeric changes.

## Evidence model

Learning now keeps two online means:

1. Global: `(npc_id, need, target_entity_id)`
2. Contextual: `(npc_id, need, context_key, target_entity_id)`

Every completed need-driven plan updates both levels using an O(1) online mean.

## Sparse-context fallback

A contextual score is not trusted immediately. Until `contextual_min_samples` is reached for a target in the current context, target ranking uses the global empirical mean as fallback. This avoids overfitting to a single contextual outcome.

After enough contextual evidence exists, ranking uses the contextual mean.

## Deterministic exploration

Exploration remains deterministic. Targets with fewer contextual samples than `exploration_samples` are preferred until enough local evidence exists. There is no random sampling.

## Causality

The context used for learning is the context captured when the target was chosen, not the context at plan completion. This matters when a trip spans several ticks and weather, danger or period changes before arrival.

## Example

A resting place can be learned as effective during the day but ineffective at night. Once both contexts have sufficient evidence, the same NPC can choose different targets for the same `energy` need without an LLM.

## Non-goals

This is not a neural policy, reinforcement-learning network, or authoritative-world mutation. The learned state is compact, inspectable and separate from world replay.
