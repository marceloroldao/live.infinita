# Life Gate 019 — Sparse Higher-Order Structural Context

## Objective

Use the representational failure demonstrated by Life Gate 018 to justify the smallest possible higher-order presemantic structural primitive.

Gate 018 established a deterministic physical truth table:

    a0 + c0 -> d1
    a0 + c1 -> d2
    a1 + c0 -> d2
    a1 + c1 -> d1

while every single antecedent-to-consequence pair remained only approximately 0.5 reliable.

Gate 019 must recover that structure without semantic conjunction labels, without creating a synthetic combined pattern ID, without generating the Cartesian product of all observed patterns, and without replacing pairwise temporal learning globally.

## bit.analyze responsibility

`SparseContextAssociator` lives in bit.analyze.

It stores an observed higher-order association as an unordered tuple of two opaque antecedent pattern IDs followed by one opaque consequence pattern ID.

No new pattern identity such as `A_AND_C` is created.

## Sparse generation

A candidate context is observed only when both antecedents actually occur in the same RealitySlice, they are temporally close enough to fit `context_span`, the consequence occurs later than both, and it is within `max_consequence_delay`.

Only observed triples are indexed.

## Evidence

Each context link tracks rho, independent-slice repetition, mean consequence delay, delay variance, context coverage, temporal stability and supporting RealitySlice IDs.

Context reliability is `context_coverage × temporal_stability`.

## Lower-order necessity gate

Higher-order structure is admitted only if both simpler antecedent-to-consequence relations remain insufficient.

For the balanced XOR corpus:

    a0 -> d1 ≈ 0.5
    c0 -> d1 ≈ 0.5
    {a0,c0} -> d1 = 4/4

Thus the conjunction is supported while neither member alone resolves the outcome. If either lower-order relation is already reliable enough, the higher-order context is not admitted.

## Live integration

`higher_order_context_selector.py` reads world-owned higher-order evidence policy, instantiates the sparse context learner, asks bit.analyze for admitted contexts, packages only admitted contexts, and preserves independent slice/frame provenance.

The Live layer does not generate missing combinations.

## Memoria.ia V2 responsibility

Memoria.ia adds a separate evidence type: `StructuralContextObservationMemory`.

Stored form: two opaque antecedent addresses plus one opaque consequence address. The pair remains a tuple; no combined address is created.

The new memory does not replace `StructuralTemporalObservationMemory`.

## Context recall

`recall_structural_context()` requires exactly two antecedent addresses. A single-pattern query is rejected.

If one exact context has one supported consequence, that consequence is recalled. If multiple consequences independently become supported for the same exact context, all remain visible; metric scores do not silently select a winner.

## Gate corpus

Gate 019 repeats all four XOR combinations four times:

    4 × a0,c0 -> d1
    4 × a0,c1 -> d2
    4 × a1,c0 -> d2
    4 × a1,c1 -> d1

Total: 16 independent RealitySlices.

Expected higher-order candidates:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

Exactly four contexts should be admitted.

## Expected evidence

For every admitted context: repetitions = 4; independent slices = 4; context coverage = 1.0; context reliability > 0.99; both lower-order reliabilities ≈ 0.5; provenance contains the four supporting RealitySlices and sixteen originating sensor frames.

## No synthetic pattern

The pairwise learner still contains exactly seven individual observable pattern IDs: d0, d1, d2, a0, a1, c0, c1.

The higher-order layer stores tuples over those IDs. It must not introduce an eighth pattern representing a conjunction.

## Memoria.ia acceptance

After transport into `StructuralContextObservationMemory`, exact recalls must produce:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

A query containing only one antecedent is not a valid higher-order query. The pairwise temporal memory remains separate and unchanged by the context adapter.

## Semantic boundary

Transport and memory payloads contain no XOR, AND, Wind, Water, barrier, gust/lull, clear/blocked, physical case labels or causal predicates.

The structure is defined only by opaque pattern identity, timing, recurrence, evidence and provenance.

## Invariants

- higher-order structure is justified by a demonstrated lower-order failure;
- only observed antecedent pairs are considered;
- antecedents must be temporally local;
- consequence must follow the complete context;
- no synthetic conjunction pattern is created;
- no full combinatorial product is generated;
- lower-order sufficiency suppresses unnecessary higher-order admission;
- context support is independent-slice based;
- Memoria.ia stores higher-order evidence separately from pairwise evidence;
- exact two-pattern recall solves the Gate 018 XOR table;
- one-pattern recall cannot bypass the context requirement;
- result is deterministic.

## Next gate

Life Gate 020 should test whether the sparse higher-order primitive remains bounded as the number of simultaneously observed patterns grows.

The target should be a distractor-rich RealitySlice where many unrelated patterns are present but only a small recurrent context pair predicts the consequence.

The gate should measure indexed higher-order candidates, admitted/observed ratio, memory growth, rejection of distractor contexts and deterministic equivalence across fragmented or reordered input.