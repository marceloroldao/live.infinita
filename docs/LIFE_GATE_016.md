# Life Gate 016 — Contextual Discrimination Without Causal Labels

## Objective

Test whether a repeated temporal association survives when the same agent signal appears
under two different physical contexts that produce different consequences.

Gate 015 learned:

\`\`\`text
a0 -> d1
\`\`\`

from repeated gust episodes.

Gate 016 holds \`a0\` constant but introduces a third world-owned condition:

\`\`\`text
barrier_01
\`\`\`

The barrier can be:

\`\`\`text
ctx_clear
ctx_blocked
\`\`\`

and is sensed only through opaque bands:

\`\`\`text
ctx_clear   -> c0
ctx_blocked -> c1
\`\`\`

No semantic causal rule is inserted into bit.analyze or Memoria.ia.

## Physical order

Each episode has the same Wind signal:

\`\`\`text
a0
\`\`\`

Wind always executes:

\`\`\`text
wind_open_channel
\`\`\`

The third condition is applied after Wind and before Water:

\`\`\`text
Wind action
    ↓
context constraint
    ↓
Water distributed physics
    ↓
sensor consequence
\`\`\`

### Clear context

\`\`\`text
a0
c0
Wind opens channel
barrier keeps channel available
Water evolves
d1
\`\`\`

### Blocked context

\`\`\`text
a0
c1
Wind opens channel
barrier closes channel
Water evolves
d2
\`\`\`

Thus the same agent signal does not uniquely determine the Water consequence.

## Four-frame RealitySlice

Gate 016 uses four sensor frames:

\`\`\`text
frame 0: Water pre-state d0
frame 1: agent signal a0
frame 2: context signal c0 or c1
frame 3: Water consequence d1 or d2
\`\`\`

The RealitySlice receives only opaque sensor pattern identities.

## Directional reliability

The existing bit.analyze selectivity metric measures relative co-occurrence strength,
but does not answer:

\`\`\`text
"When antecedent A appears, how often does B actually follow?"
\`\`\`

Gate 016 adds two generic structural metrics to bit.analyze:

\`\`\`text
directional_coverage
directional_reliability
\`\`\`

For a dominant forward relation:

\`\`\`text
directional_coverage =
    pair repetitions / slices containing the antecedent
\`\`\`

\`directional_reliability\` multiplies that coverage by the dominant direction
confidence.

This remains temporal/structural evidence, not a causal probability.

## Expected mixed-context evidence

With:

\`\`\`text
4 clear episodes
4 blocked episodes
\`\`\`

the agent signal \`a0\` appears in all 8 episodes.

But:

\`\`\`text
a0 -> d1 occurs in 4/8
a0 -> d2 occurs in 4/8
\`\`\`

Therefore both have directional reliability near:

\`\`\`text
0.5
\`\`\`

Gate 016 requires:

\`\`\`text
min_directional_reliability = 0.75
\`\`\`

Both uncontextualized pairs are rejected by:

\`\`\`text
insufficient-directional-reliability
\`\`\`

No universal \`a0 -> Water consequence\` relation enters Memoria.ia.

## Context-specific evidence

The context signals are specific:

\`\`\`text
c0 -> d1 occurs in 4/4 clear episodes
c1 -> d2 occurs in 4/4 blocked episodes
\`\`\`

Their directional reliability remains near 1.0.

They can cross the same evidence gate without any special semantic exception.

Unobserved crossed pairs remain absent:

\`\`\`text
c0 -> d2 does not exist
c1 -> d1 does not exist
\`\`\`

## Memoria.ia behavior

After ingestion of admitted candidates:

Recall from \`a0\` must not return either \`d1\` or \`d2\` as a supported universal
after-query continuation.

Recall from \`c0\` can expose \`d1\`.

Recall from \`c1\` can expose \`d2\`.

Memoria.ia still stores only opaque pattern addresses and evidence/provenance.

## World-owned context runtime

Module:

\`environmental_context_runtime.py\`

The runtime reads a world entity state and applies declared physical route constraints.

It has no dependency on:

- Nov;
- Memoria.ia;
- bit.analyze;
- temporal evidence.

The selected contextual state and route override are recorded in authoritative
Event/Delta history.

## Semantic boundary

Cognitive payloads do not contain:

- barrier;
- clear/blocked labels;
- Wind;
- Water;
- flow;
- cause/causes;
- universal rule labels.

The structural learner only sees opaque pattern identities.

## Invariants

- the Wind signal is identical in both contexts;
- Wind performs the same action in both contexts;
- the third physical condition changes the actual Water consequence;
- contextual state is world-owned;
- contextual application is read-only over its input world;
- exact context state remains outside public sensor events;
- uncontextualized agent-consequence reliability falls to approximately 0.5;
- context-specific consequence reliability remains approximately 1.0;
- unreliable universal pairs are rejected;
- reliable contextual pairs can be admitted;
- Memoria.ia does not promote \`a0\` to a universal Water rule;
- no causal label is created;
- output is deterministic.

## Next gate

Life Gate 017 should move from static per-episode context to **context that evolves on its
own trajectory**.

A useful next experiment is to make the third condition another persistent agent or
environmental process whose state changes over time. Then the system can learn:

\`\`\`text
agent signal
+ context trajectory
+ consequence trajectory
\`\`\`

without manually providing a semantic conjunction.

The central question becomes whether higher-order context can emerge from overlapping
pairwise temporal structure or whether bit.analyze needs a native multi-pattern
contextual association primitive.
