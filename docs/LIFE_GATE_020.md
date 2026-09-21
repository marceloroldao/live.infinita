# Life Gate 020 — Distractor-Rich Higher-Order Boundedness

## Objective

Stress the sparse higher-order primitive introduced in Life Gate 019 with a much larger observable pattern universe and verify that transient noise does not expand higher-order state.

Gate 020 is not a new semantic capability. It is a boundedness and determinism gate.

## Stress corpus

The physical XOR structure remains unchanged:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

Each of the four combinations is repeated five times, giving 20 independent RealitySlices. The first occurrence can serve as recurrence warm-up; the original evidence thresholds are not relaxed.

Each RealitySlice is then augmented with:

- 48 one-shot distractor patterns placed near the useful context window;
- 8 recurrent distractor patterns placed outside the useful context-span/consequence-delay window.

Across the full corpus the pairwise pattern universe therefore contains:

    7 useful patterns
  + 960 one-shot distractor IDs
  + 8 recurrent distractor IDs
  = 975 individual pattern IDs

## Recurrence prefilter

Gate 020 enables:

    min_pattern_support = 2

in the sparse higher-order associator.

A pattern must recur independently before it becomes eligible for higher-order indexing.

This prefilter does not admit evidence. It only prevents one-shot structural noise from allocating higher-order links.

After indexing, the existing gates still apply:

- context-span locality;
- consequence delay;
- repetition;
- independent RealitySlice support;
- rho;
- context reliability;
- lower-order insufficiency.

## Warm-up cost

With `min_pattern_support=2`, the first occurrence establishes recurrence eligibility and is not counted as higher-order evidence. Gate 020 therefore uses five observations per physical combination so the original `min_rho=0.39` threshold remains unchanged. This is intentionally stricter than lowering the evidence threshold to compensate for the prefilter.

## Expected boundedness

The clean Gate 020 corpus and the noisy Gate 020 corpus must have the same higher-order structure.

Expected metrics:

    clean pairwise pattern IDs: 7
    noisy pairwise pattern IDs: 975

    clean higher-order indexed links: 8
    noisy higher-order indexed links: 8

    clean admitted contexts: 4
    noisy admitted contexts: 4

    clean Memoria.ia context records: 4
    noisy Memoria.ia context records: 4

The admitted/observed higher-order ratio is therefore:

    4 / 8 = 0.5

The important property is not the ratio itself; it is that increasing the individual pattern universe from 7 to 975 does not increase the higher-order index.

## One-shot distractors

The 960 one-shot patterns are deliberately placed near the useful temporal region.

Without recurrence prefiltering they could generate many provisional higher-order combinations.

With `min_pattern_support=2`, none of them may appear in any higher-order link.

## Recurrent distractors

The 8 recurrent distractors are legitimate recurring patterns rather than one-shot noise.

They are placed outside both the useful context-span and consequence-delay windows.

They remain visible to pairwise temporal analysis but must not become admitted higher-order contexts.

This separates recurrence from contextual relevance.

## Order invariance

The same distractor-rich RealitySlices are ingested twice:

- normal occurrence tuple order;
- reversed occurrence tuple order.

The following must remain identical:

- pairwise pattern-support map;
- higher-order link signature;
- admitted higher-order candidates;
- Memoria.ia structural-context snapshot.

This validates that tuple ordering is not hidden state.

## Clean/noisy observational equivalence

The final context-memory contract from the noisy corpus must equal the clean corpus contract exactly.

Noise may expand pairwise observations, but it must not change:

- antecedent context identity;
- consequence identity;
- independent supporting RealitySlices;
- candidate identity;
- final Memoria.ia records.

## Architectural result

Gate 019 proved that higher-order structure was necessary.

Gate 020 tests whether that structure can remain sparse.

The intended path is now:

    raw recurring patterns
        -> pairwise recurrence
        -> recurrence prefilter
        -> temporally local observed context
        -> higher-order evidence gate
        -> sparse context memory

rather than:

    all observed patterns
        -> full pair Cartesian product
        -> combinatorial context graph

## Next gate

If Gate 020 is green, Life Gate 021 should stress recurring distractors that are temporally close enough to enter the higher-order index but statistically unrelated to the consequence.

That gate should test whether context coverage, lower-order insufficiency and independent provenance are sufficient to reject false recurrent contexts when temporal locality alone can no longer filter them.