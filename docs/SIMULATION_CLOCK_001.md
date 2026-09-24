# Simulation Clock 001

## Objective

Separate world progression from renderer FPS and server wall-clock time.

## Clock model

`SimulationClock` persists:

- `tick`
- `tick_duration_ms`
- `paused`
- derived `logical_time_ms = tick * tick_duration_ms`

The default duration is 500 ms per logical tick, but wall-clock scheduling is deliberately not enabled yet.

## World tick

`WorldTickRunner.tick()`:

1. checks whether the logical clock is paused;
2. advances the logical tick exactly once;
3. snapshots active plans;
4. sorts them by `plan_id` for deterministic ordering;
5. invokes at most one `PlanScheduler.tick(plan_id)` per active plan;
6. returns the resulting logical clock and plan-step summaries.

A world tick is therefore independent from Godot FPS. Rendering can run at 30/60 FPS while simulation remains at a much lower logical cadence.

## Determinism

Given the same persisted clock, active plans and authoritative state, the same world tick must process plans in the same order.

Wall time is not part of the ordering or state transition contract.

## Pause / resume

When paused:

- logical tick does not advance;
- no plan step is executed;
- renderer may continue drawing the latest state.

## Restart safety

The clock is persisted atomically. Restarting the process preserves the current logical tick and configured tick duration.

## Current activation policy

There is intentionally no background server loop yet. `WorldTickRunner.tick()` is explicit so cadence, concurrency and leader-election semantics can be defined before autonomous progression is enabled.

## Next stage

Define a server-side tick driver with:

- single-writer ownership;
- monotonic wall-clock trigger;
- no catch-up storm after downtime;
- configurable logical cadence;
- pause/resume controls;
- observability of tick latency and skipped triggers.
