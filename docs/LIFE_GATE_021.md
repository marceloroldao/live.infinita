# Life Gate 021 — Recurrent Local Distractor Rejection

## Objective

Remove both easy protections used by Life Gate 020.

In Gate 021 the distractors are:

- recurrent in every RealitySlice;
- temporally inside the same context window as the true agent/context patterns.

They therefore pass both recurrence prefiltering and temporal-locality filtering.

The gate asks whether evidence quality alone can prevent false higher-order contexts from reaching Memoria.ia.

## Corpus

The physical XOR structure remains unchanged:

    {a0,c0} -> d1
    {a0,c1} -> d2
    {a1,c0} -> d2
    {a1,c1} -> d1

Five observations are used for each physical combination, preserving the recurrence warm-up behavior introduced in Gate 020.

Total RealitySlices: 20.

## Recurrent close distractors

Eight opaque distractor patterns are inserted into every RealitySlice.

They are placed between the agent and context observations, inside context_span of both.

They are also mutually close enough that they behave as context antecedents rather than as later consequences.

Every distractor therefore has pattern support = 20.

Pairwise observable universe:

    7 useful patterns
  + 8 recurrent close distractors
  = 15 pattern IDs

## Expected higher-order expansion

Unlike Gate 020, recurrence/locality can no longer suppress these patterns before indexing.

The expected higher-order index contains:

- 4 true agent/context consequence links;
- 4 d0/agent consequence links;
- 32 agent/distractor consequence links;
- 32 context/distractor consequence links;
- 56 distractor/distractor consequence links.

Total expected observed higher-order links:

    128

## Evidence separation

The four true XOR contexts have context reliability near 1.0.

False recurrent contexts occur across multiple physical outcomes. Their consequence coverage therefore remains split instead of becoming deterministic.

With the deterministic corpus ordering and recurrence warm-up, the maximum false-context reliability is expected below 0.60, still below the configured admission threshold 0.75.

## Admission target

Expected:

    observed higher-order links = 128
    admitted contexts = 4
    Memoria.ia context records = 4

Admission ratio:

    4 / 128 = 0.03125

No distractor pattern may appear in an admitted candidate or persisted structural-context observation.

## Recall

A true exact two-pattern query must continue resolving the XOR consequence.

A false query containing one true signal plus one recurrent distractor must return no supported context neighbor.

## Order invariance

The full corpus is also ingested with every RealitySlice occurrence tuple reversed.

Pattern support, higher-order link signature, admitted candidates and Memoria.ia snapshot must remain identical.

## Architectural meaning

Gate 020 showed that one-shot noise can be removed before allocation.

Gate 021 asks a harder question:

    what if the noise is real, recurrent and temporally plausible?

If this gate passes without a new rule, then context coverage and consequence consistency are sufficient to reject this class of recurrent false context.

## Next gate

If Gate 021 is green, Life Gate 022 should make recurrent distractors conditionally correlated with outcomes for finite periods, then change regime.

That would test whether forgetting and temporal regime changes can remove formerly plausible false contexts rather than only rejecting stationary noise.

## CI acceptance

The reference run must be created after the workflow includes `test_life_gate_021_crossrepo.py`; earlier green runs from documentation-only commits are not valid Gate 021 acceptance evidence.
