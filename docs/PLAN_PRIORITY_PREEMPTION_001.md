# Plan Priority and Preemption 001

## Goal

Allow one actor to carry multiple persistent goals without executing conflicting plans at the same time.

The policy is deterministic and ledger-backed. A higher-priority plan may preempt a lower-priority plan for the same actor, while preserving the preempted plan cursor so it can resume later.

## Plan fields

Plan Ledger v2 stores:

- `priority` integer
- `actor_entity_id`
- `waiting_reason`
- `preempted_by_plan_id`
- existing `next_step_index` and completed-step provenance

Default priority is `0`.

## Arbitration

Before character plans execute in a logical tick, `PlanArbiter` groups executable plans by actor.

For each actor, ranking is:

1. higher `priority`
2. older `created_at_unix`
3. lexicographically smaller `plan_id`

Only the winner is runnable for that actor during the tick.

Plans belonging to different actors do not compete.

## Preemption

If a lower-priority plan is `planned` or `running` while another plan wins, the lower-priority plan becomes:

```text
status = waiting
waiting_reason = preempted
preempted_by_plan_id = <winner>
```

The plan is not cancelled and its `next_step_index` is not reset.

## Resume

After the dominating plan becomes terminal (`completed`, `failed`, or `cancelled`), the highest-ranked preempted plan becomes `running` again.

Its previous cursor is retained, so it resumes from the next unexecuted step rather than restarting.

## Blocked plans

Plans in `replanning`, or `waiting` for reasons other than preemption, do not participate in priority arbitration and therefore do not block another runnable plan for the same actor.

## Conditional priorities

A conditional rule that emits an intent plan may set:

```json
{"plan_priority": 100}
```

inside its metadata. `ConditionalPlanDispatcher` propagates that value into the Plan Ledger.

Example policy:

- casual conversation: priority 10
- routine task: priority 20
- urgent assistance: priority 70
- immediate danger response: priority 100

The numeric scale is policy, not engine semantics; only relative ordering matters.

## Example

NPC is executing:

```text
priority 10: walk to Nov and talk
```

A deterministic fire-danger condition creates:

```text
priority 100: move away from fire
```

The next World Tick arbitration yields:

```text
walk-to-Nov -> waiting/preempted
escape-fire -> runnable
```

When `escape-fire` becomes terminal:

```text
walk-to-Nov -> running
```

at the same `next_step_index` it held before preemption.

## Tick order

Relevant ordering is now:

1. Simulation Clock advances
2. time-scheduled events fire
3. conditional rules evaluate and may create plans
4. PlanArbiter reconciles priority conflicts
5. one step of each winning actor plan executes
6. authoritative state is available to spatial/render layers

This means an emergency condition created in tick N can preempt a routine plan before the routine plan executes in the same tick N.

## Safety and provenance

Preemption changes only plan scheduling state. It does not bypass `MutationGate`.

Every actual plan step still requires a guarded authoritative mutation and retains its mutation decision ID, world event ID, and resulting state hash.
