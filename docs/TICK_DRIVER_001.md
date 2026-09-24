# Tick Driver 001

## Goal

Drive the logical simulation clock from wall time without making wall time authoritative.

## Core rule

Wall time only decides **when to attempt the next logical tick**. It never decides how many logical ticks must be replayed.

If the server is offline for 20 minutes, restart performs the next logical tick only. There is no catch-up burst.

## Single-writer

`SingleWriterTickLease` uses a persistent lock file plus kernel `flock()` ownership:

- only one process on the host can advance authoritative ticks;
- a competing writer receives `lease_busy` and does not call `WorldTickRunner`;
- if the writer process dies, the kernel releases the lock automatically;
- the lock file remains available for operator observability.

Default path when wired by deployment:

`DATA_DIR/world-tick.lock`

## Cadence

The driver reads `SimulationClock.tick_duration_ms` for each loop. The current default is 500 ms.

A driver iteration:

1. acquire the single-writer lease;
2. call `WorldTickRunner.tick()` exactly once;
3. release the lease;
4. sleep until the next cadence boundary relative to the current iteration only.

No elapsed-time accumulator exists, therefore a delayed iteration does not create extra logical ticks.

## Pause semantics

Pause remains owned by `SimulationClock`. A driver may wake on schedule while the clock is paused, but `WorldTickRunner.tick()` returns `advanced=false` and executes no plan step.

## Activation policy

This feature is not automatically enabled by the runtime or systemd yet. `tick_driver_main.py` is an explicit helper for a future dedicated simulation process.

Before production activation we should define:

- process/service ownership;
- shutdown and health semantics;
- multi-host/distributed lease strategy if the runtime becomes clustered;
- operator controls for pause/resume and tick duration.

## Invariants

- one authoritative tick writer per host;
- at most one logical tick per driver iteration;
- downtime never becomes a backlog;
- renderer FPS does not influence logical time;
- plan ordering remains deterministic inside `WorldTickRunner`;
- autonomous simulation remains opt-in until deployment policy is frozen.
