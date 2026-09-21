# Life Gate 028 — Event Time vs Arrival Order

## Objective

Separate RealitySlice event time from network/arrival order.

A delayed slice that is still inside bounded lateness must be preserved and reordered. A slice older than the current watermark must not silently re-enter current structural evidence or move learner time backward.

## Bounded-lateness reorder layer

`RealitySliceReorderBuffer` is upstream of both temporal learners.

It tracks:

- `max_event_time`: maximum observed RealitySlice `t_end`;
- `watermark = max_event_time - allowed_lateness`;
- pending accepted slices;
- explicit late rejections.

Accepted pending slices are emitted deterministically by:

    (t_end, t_start, slice_id)

Gate 028 configures:

    allowed_lateness = 4.0

## Arrival-order stress

The same 20 relevant RealitySlices are ingested in two arrival sequences:

    in-order

and four-slice blocks arriving as:

    4, 2, 1, 3

The latter is out of arrival order but remains within the configured lateness bound.

Both streams must be emitted to `TemporalAssociator` and `SparseContextAssociator` in exactly the same event-time sequence.

## Shared ingest bridge

`reality_slice_event_time_runtime.py` ensures every emitted slice is applied in this order:

    reorder buffer
        -> TemporalAssociator
        -> SparseContextAssociator

The higher-order learner receives the pairwise pattern-support map only after the pairwise learner ingests the same emitted slice.

This prevents the two structural layers from observing different temporal trajectories.

## Too-late conflict

After the maximum event time has advanced enough, Gate 028 injects one old RealitySlice with:

    event time = 10.0

while the watermark is already later.

The late slice contains a deliberately conflicting physical pattern:

    {a0,c0} -> d2

where the valid world relation is:

    {a0,c0} -> d1

The conflicting slice must be returned as `LateRealitySliceRejection` and must never enter either associator.

## Rejection contract

A rejection records:

- slice ID;
- event time;
- current watermark;
- reason: `event-time-before-watermark`.

Rejection is explicit and audit-preserving. It is not silently discarded inside a learner.

Duplicate slice IDs are rejected with an error rather than counted twice.

An event exactly on the watermark boundary remains accepted.

## Expected invariance

For in-order and bounded out-of-order arrival:

- emitted slice sequence is identical;
- pairwise signatures are identical;
- higher-order signatures are identical;
- current candidate sets are identical;
- resolution states are identical;
- current Memoria.ia admission is identical.

For the too-late conflicting slice:

- watermark does not move backward;
- max event time does not move backward;
- rejected slice ID never appears in higher-order `seen_slices`;
- rejected slice ID never appears in higher-order `slice_end_times`;
- candidates and resolutions remain identical to the clean stream;
- active recall remains on the valid consequence.

## Architectural meaning

Gate 027 established physical-time evidence windows.

Gate 028 adds the necessary input condition:

    event time is authoritative;
    arrival order is transport behavior.

A network packet may arrive late without rewriting the past. Bounded-late evidence is reordered into the event-time trajectory; evidence beyond the watermark is quarantined from current cognition with an explicit audit record.

## Invariants

- watermark is monotonic;
- max event time is monotonic;
- bounded-late slices are preserved;
- too-late slices are not learned;
- learner clocks never move backward through the supported ingest path;
- no semantic source priority is introduced;
- deterministic replay produces identical results.

## Next gate

If Gate 028 is green, Life Gate 029 should test multiple independent source clocks and clock skew.

The target is to determine how event-time normalization should behave when two sensors disagree on absolute time but preserve local sequence, without allowing one bad clock to advance the global watermark incorrectly.