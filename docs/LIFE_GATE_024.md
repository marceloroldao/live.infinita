# Life Gate 024 — Reacquisition After Passive Forgetting

## Objective

Test whether a higher-order context that was learned, passively forgotten, and later observed again can become active naturally without restoring historical strength before fresh evidence arrives.

Gate 024 does not add a new learning rule in advance.

## Three phases

Phase 1 — learning:

    {a0,x0} -> d1
    {a1,x0} -> d2

The proxy context is genuinely admitted.

Phase 2 — passive forgetting:

    x0 disappears completely

Global higher-order time advances. Proxy rho decays below min_rho. Historical observations remain, but active admission becomes empty.

Phase 3 — return:

    x0 returns in the same structural context as phase 1

The existing link receives new real observations and may recover admission.

## No historical reset

Before any phase-3 observation, the link must still be in its forgotten state.

The first returning observation must update rho from the decayed value through the normal SparseContextAssociator reinforcement equation.

The implementation must not restore:

- phase-1 peak rho;
- old active admission;
- synthetic repetitions;
- synthetic provenance.

## Candidate identity

The reacquired structure should retain the same opaque candidate identity because the antecedent tuple and consequence are the same.

New supporting RealitySlices are added to the existing structural provenance.

Therefore the reacquired candidate preserves continuity without pretending that old evidence happened again.

## Admission-state transition

Memoria.ia admission history should record:

    phase-1: active
    phase-2: inactive
    phase-3: active

Historical StructuralContextObservationMemory remains additive throughout.

## Recall

At the end of phase 2:

    historical recall -> old consequence remains visible
    active recall     -> empty

At the end of phase 3:

    historical recall -> consequence visible
    active recall     -> consequence visible again

## Reacquisition speed

Gate 024 also runs a fresh learner from zero over the same returning observations.

The experiment records the first round in which each proxy context becomes admitted.

Reacquisition may be faster than first learning because residual decayed evidence is part of the actual memory state.

This is accepted only if:

- no admission occurs before a real returning observation;
- rho starts from the decayed state, not the historical peak;
- each returning support adds a new slice/repetition;
- candidate provenance expands with fresh evidence.

## True structure

The real XOR contexts continue to be observed through all phases and must remain active after reacquisition.

## Invariants

- no product-code rule is added solely to force reacquisition;
- forgotten state is below min_rho before return;
- first return increases rho from the decayed value;
- repetitions and seen_slices increase only on actual returning observations;
- candidate ID is stable across learn/forget/relearn;
- supporting provenance strictly expands after reacquisition;
- admission history is active -> inactive -> active;
- active recall returns only after new evidence;
- historical recall remains auditable;
- deterministic replay produces identical results.

## Next gate

If Gate 024 is green, Life Gate 025 should test relearning after the returning context has changed meaning.

That gate should distinguish:

- reacquisition of the same old relation;
- learning a new consequence for the same antecedent context;
- coexistence versus replacement in historical memory;
- current admission under competing post-forgetting outcomes.