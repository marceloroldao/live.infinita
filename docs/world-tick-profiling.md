# World Tick latency profiling (opt-in)

The authoritative world driver remains the single writer. Profiling is passive,
disabled by default and cannot grant mutation authority or create additional
ticks. Only aggregate stage timings are recorded; world payloads, identities,
memory contents and prompts are not included.

## Enable and inspect

Set `LIVE_INFINITA_TICK_PROFILER=1` in the authorized service environment and
restart the autonomous-world service under the existing deployment procedure.
Do not start a second World Tick process to collect measurements.

Read `<LIVE_INFINITA_DATA_DIR>/world-tick-profile.json`. The report is replaced
atomically every 32 executed ticks and uses a rolling window of at most 256
samples, so there is no unbounded telemetry journal. Disabling the flag on the
next restart stops recording. Existing reports are historical snapshots and
should not be mistaken for live state.

Fields:
- `generated_at_unix` and `process_pid`: distinguish a live report from a stale prior-process snapshot.
- `total_observed_ticks`: since the current process started (resets on restart).
- `window_samples`: rolling sample count, at most 256.
- `tick_budget_ms`: configured tick interval (normally 500 ms).
- `total`: observed wall-clock tick duration, p50/p95/p99/max.
- `over_budget_ticks` and `over_budget_ratio`: within the rolling window.
- `stages`: per-stage p50/p95/p99/max and number of observed ticks.
  Repeated `plans.tick` durations are aggregated within a single tick.
- `unaccounted`: total duration minus measured stage durations (clamped to
  zero). This includes result projection, uninstrumented work and observation
  overhead; it must not automatically be attributed to one subsystem.
- `slow_threshold_ms` is 1000 ms. `slow_tick_count` counts all such
  ticks in the rolling window; `slowest_ticks` includes at most the 12 slowest,
  identified by authoritative `logical_tick` and `sample_index`. Each row
  includes total wall time, unaccounted time and measured `stages_ms`.
  This is correlation evidence, not a CPU stack or proof of a stage's cause.
  No world payloads, NPC identity, memory text or actions are persisted.

The optional telemetry must never mutate or pause the world. If a metric callback
fails, the driver proceeds; persistence errors do not restart the service.

## Investigation order

1. Confirm service is active, PID stable, NRestarts unchanged and clock advances.
2. Confirm no new duplicate composite strategies or unexpected JSONL growth.
3. Collect at least 256 samples and inspect total p95 and the stage p95 values.
4. Optimize the measured bottleneck, preserve authoritative JSONL and replay
   semantics, and validate on an isolated worktree before production deployment.
5. Re-run the same sampling window to compare before/after.

A 500 ms interval is a **budget**, not proof of meeting real-time cadence.
A sampled gate may require at least 256 samples, total p95 <= 500 ms and
over-budget ratio <= 5%; the gate must fail when the report is missing or stale.

## 24-hour simulated-life acceptance (later milestone)

At 500 ms logical increments, 24 hours of simulated time are **172,800 ticks**.
Measure start/end logical tick, actual wall-clock duration, process restarts,
rolling profile snapshots, RAM high-water mark, persistent ledger growth,
invalid/torn records, duplicate in-flight NPC goals and restart/replay fidelity.

This is not completed merely by passing a 256-sample profile window; it requires
the full 172,800 successful authoritative ticks. Do not reset or truncate a
production ledger to run the gate. Prefer an isolated persistent test world with
a separate data directory and lease, then a controlled live observation.
