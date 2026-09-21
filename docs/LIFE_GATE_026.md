# Life Gate 026 — Gradual Higher-Order Remapping

## Objective

Validate a gradual transition between two higher-order mappings without choosing a winner prematurely.

The same opaque antecedent context evolves from an old consequence to a new consequence while the active evidence window temporarily contains both.

## Window geometry

Gate 026 keeps the 20-RealitySlice active evidence window from Gate 025.

One physical round contributes four RealitySlices. Therefore the window contains five rounds.

Five initial rounds establish the old mapping. Then four consecutive rounds use the new mapping.

For each exact proxy context, current coverage evolves as:

    transition-1: old 0.8 / new 0.2
    transition-2: old 0.6 / new 0.4
    transition-3: old 0.4 / new 0.6
    transition-4: old 0.2 / new 0.8

The admission threshold remains 0.75.

## Expected state sequence

    initial       -> resolved old
    transition-1  -> resolved old
    transition-2  -> ambiguous
    transition-3  -> ambiguous
    transition-4  -> resolved new

No threshold is changed during the transition.

## Explicit ambiguity

Gate 026 distinguishes:

- resolved: exactly one candidate is currently admitted;
- ambiguous: multiple higher-order consequences have current evidence but none is uniquely admitted;
- unsupported: no current higher-order continuation has enough structural support.

Ambiguity is not stored as a new structural observation.

During an ambiguous state:

    active_candidate_ids = ()

while:

    competing_candidate_ids = (opaque candidate IDs...)

records the structural competition for audit.

## Memoria.ia

`StructuralContextAdmissionStateMemory` now stores:

- `resolution_state`;
- `competing_candidate_ids`.

If an older caller supplies multiple active candidate IDs, the state is normalized to explicit ambiguity with zero active candidates.

Historical `StructuralContextObservationMemory` remains unchanged.

Therefore an ambiguous transition does not create a fact and does not erase old history.

## Live resolution projection

`resolve_higher_order_context_states()` is a read-only projection over bit.analyze links.

It considers only links that still require higher-order representation; relations already explained sufficiently by lower-order evidence are excluded from the ambiguity set.

It does not:

- create patterns;
- create links;
- change rho;
- add provenance;
- label the world semantically.

## Recall behavior

During transition-2 and transition-3:

    historical recall -> previously admitted structure remains auditable
    active recall     -> empty

At transition-4:

    active recall -> new consequence only

After the new mapping is admitted historically, historical recall exposes both old and new consequences.

## Invariants

- coverage changes arise only from the sliding recent evidence window;
- no phase label is passed into bit.analyze;
- ambiguity has zero active candidates;
- ambiguity keeps competing opaque IDs for audit;
- no score elects a winner during the mixed window;
- old history remains intact;
- final new mapping must cross the unchanged admission threshold;
- deterministic replay produces identical resolutions and memory snapshots.

## Next gate

Life Gate 027 should remove the fixed-size-window assumption by testing transition behavior across different event rates.

The target is to determine whether an evidence window measured only in number of RealitySlices is stable when one sensor/source emits much faster than another, or whether current evidence needs a time-bounded window in addition to a slice-count bound.