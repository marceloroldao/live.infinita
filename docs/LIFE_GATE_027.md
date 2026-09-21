# Life Gate 027 — Event-Rate Invariant Current Evidence

## Objective

Test whether current higher-order evidence depends on elapsed physical time or merely on how many unrelated RealitySlices were emitted.

Gate 026 used a 20-slice active evidence window. Gate 027 demonstrates the failure mode of that representation under heterogeneous event rates and introduces a time-bounded alternative.

## Relevant evidence

The world generates five complete XOR rounds, producing 20 relevant RealitySlices.

Those slices establish the same four true higher-order contexts used by earlier gates.

## Rate stress

After the relevant evidence, one second of physical time passes.

Two cases are compared:

    slow irrelevant stream: 2 one-shot slices
    fast irrelevant stream: 100 one-shot slices

The noise carries unrelated one-shot patterns and allocates no higher-order links.

The relevant world history and final physical time are identical in both cases.

Only event rate differs.

## Count-window failure

A 20-slice current evidence window behaves differently:

    slow stream
    -> relevant slices remain inside the last 20
    -> true higher-order contexts remain admitted

    fast stream
    -> the last 20 slices are all irrelevant noise
    -> relevant current support disappears
    -> the same previously resolved context becomes unsupported

This is a false deactivation caused by event rate rather than world time.

## Physical-time window

`SparseContextAssociator.recent_slice_ids_by_time(time_span, now=None)` selects slices by recorded `t_end` inside a physical-time interval.

Gate 027 configures:

    active_evidence_slice_window = 0
    active_evidence_time_window = 25.0

The 25-unit window contains all relevant evidence plus the identical one-second noise interval in both rate cases.

## Policy contract

Count and time windows are currently mutually exclusive.

This avoids silently combining two different notions of recency before such a composition has been experimentally validated.

Default values remain zero, preserving prior accumulated behavior when neither window is enabled.

## Expected invariance

Under the time window:

- slow and fast streams have the same final physical time;
- the same relevant RealitySlice IDs remain eligible;
- the same four higher-order candidates are admitted;
- candidate payloads are identical;
- current resolution states are identical;
- no noise pattern enters higher-order links;
- Memoria.ia active recall remains resolved under the fast stream.

## Memoria.ia consequence

With the count window, a previously active exact context can be falsely transitioned to `unsupported` after a burst of irrelevant events.

With the time window, the same context remains `resolved` because no relevant physical time has expired.

Historical memory is unchanged in both cases.

## Architectural meaning

A RealitySlice count is a measure of traffic volume, not time.

For multimodal systems where sensors, agents and external sources emit at different frequencies, current structural evidence must not age solely because another channel is noisy or high-frequency.

Gate 027 therefore separates:

    event density
    from
    elapsed evidence time

without adding any sensor semantics.

## Invariants

- time-window selection uses only slice timestamps;
- high-rate one-shot noise creates no higher-order links;
- relevant support is unchanged at equal physical time;
- count-window and time-window behavior are explicitly compared;
- time-window selection is read-only over historical links;
- no thresholds are changed;
- no semantic source priority is introduced;
- deterministic replay produces identical results.

## Next gate

If Gate 027 is green, Life Gate 028 should test mixed source clocks and out-of-order arrival.

The target is to separate event time from arrival/ingest order, ensuring that delayed packets do not incorrectly re-enter or evict current evidence and that watermark/reordering policy remains deterministic.