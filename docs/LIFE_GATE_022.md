# Life Gate 022 — Higher-Order Regime Shift and Active Deactivation

## Objective

Test a higher-order context that is genuinely useful in one regime and becomes unreliable after the world changes.

The goal is not deletion. The system must preserve historical evidence while removing obsolete structure from current active recall.

## Physical structure

The underlying XOR world remains unchanged:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

## Proxy signal

Gate 022 adds one opaque recurring structural pattern:

    x0

Phase 1:

    x0 appears only with c0

so the following proxy contexts become genuinely predictive:

    {a0,x0} -> d1
    {a1,x0} -> d2

Neither a0/a1 nor x0 alone resolves the consequence, so these higher-order proxy contexts can pass the normal evidence gate.

Phase 2:

    x0 appears only with c1

The same exact proxy context now precedes a different consequence:

    {a0,x0} ... d2
    {a1,x0} ... d1

Across accumulated experience, the old proxy contexts lose context coverage and are no longer admitted.

## No threshold relaxation

The existing higher-order thresholds remain unchanged.

An obsolete proxy link may retain rho above min_rho. It is deactivated because consequence consistency/context reliability falls below the current admission threshold.

This distinguishes evidence deactivation from destructive deletion.

## Historical versus active memory

StructuralContextObservationMemory remains additive and audit-preserving.

A new StructuralContextAdmissionStateMemory stores successive current-admission snapshots for each exact two-pattern context.

Phase 1 snapshot:

    {a0,x0}: active candidate = old d1 hypothesis

Phase 2 snapshot:

    {a0,x0}: active candidates = empty

`recall_structural_context()` remains historical recall and still exposes the formerly supported d1 observation.

`recall_active_structural_context()` intersects historical observations with the latest admission snapshot and therefore returns no active neighbor for {a0,x0} after phase 2.

## True structure remains active

The real XOR contexts remain deterministic through both regimes and continue to be active:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

## Audit

Admission-state history preserves both epochs.

The formerly active candidate ID is not removed from structural observation history.

The latest admission snapshot is the only layer used to decide whether a historical candidate participates in current active recall.

## Architectural meaning

Gate 022 separates three concepts that were previously conflated:

    observed in the past
    supported historically
    admitted now

Memoria.ia can therefore remember that a relationship used to work without continuing to treat it as a current prediction.

## Limitation

This gate tests regime contradiction: the same antecedent context continues to occur but with different consequences.

It does not yet test a context that disappears completely. Pure time-based decay of an unobserved context remains a separate problem.

## Next gate

Life Gate 023 should test passive forgetting when a formerly admitted context stops appearing entirely.

That gate should determine whether the bit.analyze higher-order layer needs explicit global time advancement/decay for links that receive no new observations, while preserving the same historical-versus-active memory boundary.

Temporary validation PR: this marker exists only to force a fresh Actions run against the fully updated Gate 022 branch state.
