# Life Gate 023 — Passive Higher-Order Forgetting

## Objective

Test whether a formerly admitted higher-order context loses current admission when it stops appearing entirely, without contradiction and without deleting history.

Gate 022 handled contradiction-driven deactivation. Gate 023 handles absence-driven decay.

## Phase 1

The physical XOR structure remains unchanged.

An opaque proxy pattern `x0` appears only with `c0`, making these higher-order contexts genuinely predictive:

    {a0,x0} -> d1
    {a1,x0} -> d2

Five observations per physical combination are used. With `min_pattern_support=2`, one observation establishes recurrence and four reinforce higher-order evidence.

## Phase 2

The world continues evolving through all four XOR combinations, but `x0` is never observed again.

There is no contradictory `x0` observation.

Therefore:

- proxy pattern support does not increase;
- proxy context_slices do not increase;
- proxy link repetitions do not increase;
- proxy seen_slices do not change;
- proxy last_time remains the last actual observation time.

Only world time advances.

## Global time decay

`SparseContextAssociator.advance_time(now)` decays all known higher-order links without creating observations.

`ingest()` calls `advance_time(rs.t_end)` before processing a new RealitySlice.

Each ContextAssociation separates:

- `last_time`: last actual observation;
- `last_decay_time`: latest time through which passive decay has been applied.

This prevents double decay at the same timestamp while preserving observation provenance.

Gate 023 configures the higher-order structural evidence policy:

    forgetting_lambda0 = 0.025

The existing evidence threshold remains:

    min_rho = 0.39

## Monotonic experiment time

Independent episode RealitySlices are shifted onto one monotonically increasing experimental timeline before ingestion.

This is required because passive forgetting is a relation to elapsed time, not merely to the number of independent episodes.

## Expected deactivation

At the end of phase 1, proxy contexts are admitted.

During phase 2, they are untouched but decay globally.

Expected:

    context_reliability remains > 0.99
    repetitions unchanged
    provenance unchanged
    rho falls below min_rho
    candidate leaves current admitted set

This distinguishes forgetting by elapsed time from contradiction-driven coverage loss.

## True structure remains active

The real XOR contexts continue to be observed in phase 2. Their rho is refreshed and they remain admitted:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

## Memoria.ia behavior

Historical `StructuralContextObservationMemory` retains the phase-1 proxy observation.

`StructuralContextAdmissionStateMemory` receives a phase-2 snapshot with an empty active candidate set for the vanished proxy context.

Therefore:

    recall_structural_context({a0,x0})
        -> historical d1 remains visible

    recall_active_structural_context({a0,x0})
        -> no current neighbor

No historical structural evidence is deleted.

## Invariants

- passive time advancement creates no new observations;
- repetitions and seen_slices do not change during decay;
- last observation time does not move during passive decay;
- last_decay_time advances monotonically;
- applying decay twice at the same time is idempotent;
- obsolete proxy rho falls below the unchanged admission threshold;
- true recurring contexts remain active;
- historical recall and current-active recall remain distinct;
- result is deterministic.

## Architectural result

After Gate 023, higher-order state has three independent dimensions:

    historical observation
    current evidence strength
    current admission state

A relationship can therefore be remembered, become weak through non-observation, and stop participating in current prediction without destructive deletion.

## Next gate

Life Gate 024 should test reacquisition: after a passively forgotten context returns, it should recover from new observations without losing its historical provenance or receiving an artificial shortcut from old rho.

The gate should measure reacquisition speed, provenance union, admission transitions, and whether a long absence followed by renewed evidence behaves differently from a never-forgotten context.