# NPC Goal Reordering 001

This baseline turns a declarative short-horizon recommendation into one bounded executable reorder while preserving the existing authority model.

## Rule

The base `NpcNeedScheduler` remains unchanged. The autonomous cognitive stack opts into `NpcReorderingNeedScheduler`.

A reorder is permitted only when the chosen strategy contains a `goal_sequence` with `mode=defer_current` and the first goal:

- names a known need;
- differs from the currently selected need;
- has a concrete target entity that exists in the authoritative cold store;
- is not inside its own cooldown window.

The scheduler then re-evaluates that prerequisite need once using the normal target, strategy, compiler, Proposal Ledger and PlanScheduler/StrategyExecutor path. The second evaluation is never recursively reordered.

## Example

Current state:

- curiosity is the only need above the current threshold;
- counterfactual/horizon evaluation predicts that safety will become dominant if exploration starts now;
- the declarative sequence is `safety -> curiosity`.

The scheduler may execute `safety` first even if its current scalar value is still below the ordinary threshold, because the reason is an explicit prospective prerequisite rather than a present-threshold trigger.

## Audit fields

Scheduled rows and proposal metadata include:

- `original_need`;
- effective `need`;
- `horizon_reordered`;
- `reorder_source_sequence`;
- selected target;
- priority and utility;
- complete strategy/ranking metadata.

The proposal approval reason also records `horizon reordered <original>-><effective>`.

## Fail-closed behavior

If the prerequisite target is missing, invalid, unresolved, or in cooldown, the scheduler preserves the original need. No synthetic target is invented and no extra proposal is emitted.

## Authority boundary

The horizon, goal sequence and reorder policy do not mutate world state. They select which semantic intent is proposed. Actual execution still requires:

`Proposal Ledger -> approved proposal -> StrategyExecutor/PlanScheduler -> Mutation Gate -> authoritative world`.

## Non-goals

This baseline does not execute an entire multi-goal queue automatically. It performs at most one prospective reorder for the current decision. The original goal remains represented in the source sequence and can be reconsidered on later ticks from the then-current world and need state.
