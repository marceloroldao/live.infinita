# Life Gate 025 — Post-Forgetting Higher-Order Remapping

## Objective

Test whether the same higher-order antecedent context can return after passive forgetting and now reliably precede a different consequence.

The system must preserve the old relation historically while exposing only the new relation as currently admitted.

## Three phases

Phase 1 — original mapping:

    {a0,x0} -> d1
    {a1,x0} -> d2

Phase 2 — passive forgetting:

    x0 disappears

Old proxy links decay below current admission.

Phase 3 — remapped return:

    {a0,x0} -> d2
    {a1,x0} -> d1

The antecedent context identity is unchanged. Only the physical consequence changes.

## Why global accumulated coverage is insufficient

With accumulated history only, each new consequence is penalized by the old regime:

    historical {a0,x0} occurrences = old d1 + new d2

Therefore the new consequence has roughly half of the all-time context coverage even when the current world has become fully deterministic again.

Gate 025 explicitly verifies that global accumulated admission does not resolve the new mapping.

## Recent structural evidence window

`SparseContextAssociator` now retains the exact RealitySlice IDs in which each antecedent context occurred.

It also records each slice end time and can return the most recent N slices by temporal order.

Admission may optionally evaluate:

- repetitions inside a recent slice set;
- independent support inside that set;
- context coverage inside that set.

Historical links, rho, seen_slices and global context history are not deleted or reset.

Gate 025 configures:

    active_evidence_slice_window = 20

which equals one experimental phase, but the learner receives no semantic phase label.

## Current versus historical evidence

The recent window is used only for current higher-order admission.

The continuous link still owns its global decayed/reinforced rho.

When a candidate is transported to Memoria.ia under an active evidence window:

- repetitions reflect the active window;
- supporting RealitySlice IDs reflect the active window;
- context coverage reflects the active window;
- candidate identity remains based only on antecedents + consequence.

## Expected remapping

At phase 3:

    global accumulated selector -> proxy remap unresolved

    recent selector             -> new proxy mapping admitted

Expected current mappings:

    {a0,x0} -> d2
    {a1,x0} -> d1

Old mappings must not remain in the current admitted set.

## Memoria.ia behavior

Historical structural context memory contains both old and new consequences.

For `{a0,x0}`:

    historical recall -> d1 and d2

Current admission state records only the new candidate ID.

Therefore:

    active recall -> d2 only

The old d1 relation is not deleted or score-ranked away; it is simply not in the latest admission snapshot.

## Candidate identity

Old and new consequences produce different opaque candidate IDs because consequence identity is part of the structural triple.

Both IDs remain auditable in historical memory.

## Admission-state trajectory

For one remapped context:

    phase-1: old candidate active
    phase-2: no candidate active
    phase-3: new candidate active

This is a genuine remap, not reacquisition of the old candidate.

## Invariants

- no semantic regime label enters bit.analyze;
- recent evidence is selected by structural time ordering;
- global historical links remain intact;
- old and new consequence links coexist historically;
- only the current remapped consequence is active;
- no score chooses a historical winner;
- true XOR contexts remain active;
- recent-window selection is read-only over historical support;
- deterministic replay gives identical results.

## Next gate

If Gate 025 is green, Life Gate 026 should test a gradual regime transition instead of a clean phase boundary.

The new consequence should emerge probabilistically over a sliding period so the active evidence window contains both mappings for a while.

The target is to verify an explicit ambiguous transition state before the new mapping becomes uniquely admitted, rather than forcing an abrupt winner.