# NPC Composite Strategy Execution 001

## Objective

Execute compiled NPC strategies as persistent semantic phases without bypassing the normal intent planner, plan arbitration or Mutation Gate.

## Execution model

A strategy execution has its own append-only state:

- `strategy_execution_id`
- `strategy_plan`
- `phase_index`
- `child_plan_id`
- `wait_started_tick`
- `completed_phases`
- terminal status and error

Only one strategy phase advances per logical tick.

## Movement phases

`move_to_entity` never mutates the world directly. The executor schedules a normal child plan using `PlanScheduler.schedule()` with a deterministic idempotency key:

`strategy-phase:<strategy_execution_id>:<phase_index>`

The child plan then goes through the existing planner, priority arbiter, revalidation and Mutation Gate. The strategy phase advances only after the child plan is `completed`. A failed/cancelled child fails the strategy execution.

## Wait phases

`wait_ticks` uses only Simulation Clock ticks. No wall-clock sleep is used.

If a phase begins at logical tick 100 with `ticks=3`, it becomes complete at tick 103 or later. Restart does not reset the wait because `wait_started_tick` is persisted.

## World tick ordering

When configured, `WorldTickRunner` performs the composite strategy phase before plan arbitration:

1. clock advance
2. scheduled/conditional events
3. NPC need dynamics and objective generation
4. composite strategy executor
5. plan replanning
6. plan arbitration
7. authoritative plan execution
8. need outcome feedback

This lets a movement phase create a child plan that may participate in arbitration in the same logical tick, while the composite cursor itself only advances after confirmed child completion.

## Invariants

- strategy compilation grants no authority
- strategy execution never writes world state directly
- `wait_ticks` depends only on logical time
- child-plan creation is idempotent
- restart preserves phase cursor and wait state
- a phase cannot be marked completed before its child plan is completed
- child failure fails closed
