# NPC Cognitive Runtime 001

## Purpose

Define the explicit composition boundary for deterministic autonomous NPC cognition.

The web/API runtime does not automatically own simulation time. Autonomous cognition is composed separately and may only advance through the authoritative single-writer World Tick process.

## Composition

`build_npc_cognitive_stack(...)` creates the persistent cognitive graph from runtime-owned planning and proposal services:

1. `NpcNeedDynamics`
2. `NpcNeedLearning`
3. `NpcStrategyExperience`
4. `NpcStrategyValue`
5. `NpcCompositeStrategy`
6. `NpcStrategyCompiler`
7. `NpcStrategyExecutor`
8. `NpcNeedScheduler`
9. `NpcNeedOutcomeProcessor`
10. `NpcCompositeStrategyOutcomeProcessor`

The stack does not start threads, timers or processes.

`build_autonomous_world_tick(...)` composes that stack into a `WorldTickRunner` but still does not start ticking.

`run_driver(...)` is the explicit activation boundary. It acquires the single-writer tick lease and serves the logical simulation loop.

## Learning loop

The whole composite strategy loop is:

`need -> target -> strategy -> compiled phases -> execution -> terminal need outcome -> composite outcome -> strategy experience -> future ranking`

Whole-strategy evidence is keyed by:

`npc + need + target + canonical context + strategy_id`

This allows `direct`, `via_shelter:<id>` and `wait_then_direct` to learn independently while pursuing the same final target.

## Causal invariants

1. Intermediate movement phases never satisfy the originating need.
2. Only the terminal eligible child plan receives the original proposal id.
3. Whole-strategy learning happens only after the composite execution is complete and the terminal need outcome exists.
4. Strategy outcomes are idempotent by strategy execution/outcome id.
5. Sparse strategy evidence falls back to deterministic heuristic ranking.
6. Empirical ranking is enabled only after the configured minimum sample count.
7. Cognitive components never bypass PlanScheduler, arbitration, revalidation or Mutation Gate.
8. Building the cognitive runtime never acquires the single-writer lease and never advances logical time.

## Persistence

The cognitive stack persists under its supplied data directory:

- `npc-need-state.json`
- `npc-need-learning.json`
- `npc-strategy-experience.json`
- `npc-need-scheduler.jsonl`
- `npc-strategy-executions.jsonl`
- `npc-need-outcomes.jsonl`
- `npc-composite-strategy-outcomes.jsonl`

Restarting the process reconstructs the same cognitive graph from these durable records while authoritative world mutation remains governed by the world runtime.

## Activation policy

Do not instantiate or run this stack implicitly from the legacy FastAPI `main.py`.

A deployment that enables autonomous NPC simulation must deliberately:

1. construct the authoritative planner/scheduler and proposal ledger;
2. call `build_autonomous_world_tick(...)`;
3. validate the returned runner/stack configuration;
4. pass the runner to `run_driver(...)` in the designated single-writer simulation process.
