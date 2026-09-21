# Life Gate 018 — XOR Representational Limit

## Objective

Deliberately construct a physical dependency that cannot be represented by any single
signal or any single context pattern.

The goal is diagnostic.

Gate 018 does **not** add a higher-order cognitive primitive in advance. It asks whether
the existing pairwise RealitySlice -> TemporalAssociator -> Memoria.ia path can represent
the dependency on its own.

## Physical state interaction

Gate 018 adds a generic table-driven World Runtime:

\`environmental_state_interaction_runtime.py\`

The runtime:

1. reads multiple exact World-State component values;
2. matches a world-declared case;
3. applies physical route overrides;
4. records the interaction in authoritative Event/Delta history.

The runtime contains no XOR operator and no cognitive logic.

The XOR-like behavior exists only in the world's case table.

## Inputs

The two independently observable structural inputs are:

\`\`\`text
agent signal:
a0 / a1

context signal:
c0 / c1
\`\`\`

Internally, World Runtime reads the exact phase values of:

- \`wind_01.environmental_state.phase_id\`;
- \`barrier_01.process_state.phase_id\`.

The sensor layer still exposes only opaque bands.

## Truth table

The physical rule is:

\`\`\`text
a0 + c0 -> d1
a0 + c1 -> d2
a1 + c0 -> d2
a1 + c1 -> d1
\`\`\`

The outcome is realized by controlling whether \`spring_channel\` is available before
the real distributed-Water tick.

When available, the dominant Spring transfer is \`d1\`.

When unavailable, \`spring_hollow\` becomes dominant and the consequence is \`d2\`.

Every outcome therefore comes from the existing production Water runtime and sensor
runtime.

## Learning corpus

The balanced Gate 018 corpus contains:

\`\`\`text
4 × (a0,c0 -> d1)
4 × (a0,c1 -> d2)
4 × (a1,c0 -> d2)
4 × (a1,c1 -> d1)
\`\`\`

Total:

\`\`\`text
16 independent RealitySlices
\`\`\`

Each slice contains four frames:

\`\`\`text
d0
agent signal
context signal
physical consequence
\`\`\`

## Expected pairwise evidence

For any single agent signal:

\`\`\`text
a0 -> d1 = 4 / 8
a0 -> d2 = 4 / 8
a1 -> d1 = 4 / 8
a1 -> d2 = 4 / 8
\`\`\`

For any single context signal:

\`\`\`text
c0 -> d1 = 4 / 8
c0 -> d2 = 4 / 8
c1 -> d1 = 4 / 8
c1 -> d2 = 4 / 8
\`\`\`

Directional reliability is therefore expected near:

\`\`\`text
0.5
\`\`\`

below the Gate 016+ threshold:

\`\`\`text
0.75
\`\`\`

## Signal/context pairs are also insufficient

The current TemporalAssociator stores pairwise links.

The co-occurrence pairs:

\`\`\`text
a0 -- c0
a0 -- c1
a1 -- c0
a1 -- c1
\`\`\`

also occur in only half of each signal's appearances.

They do not create a new antecedent identity such as:

\`\`\`text
(a0,c0)
\`\`\`

that could independently point to \`d1\`.

## RealitySlice representation

The bridge creates exactly seven observable pattern identities:

\`\`\`text
d0
d1
d2
a0
a1
c0
c1
\`\`\`

No synthetic conjunction pattern is created.

This is intentional.

Creating \`a0+c0\` manually would hide the representational question by pre-solving it.

## Memoria.ia consequence

Because no single pattern -> consequence relation crosses the evidence gate, Memoria.ia
cannot recall \`d1\` or \`d2\` as a supported future from any single query:

\`\`\`text
a0
a1
c0
c1
\`\`\`

The current structural temporal recall API is unary: one pattern address is the query.

Therefore the deterministic physical truth table exists in World Runtime while the
current pairwise cognitive representation remains unresolved.

## What this proves

Gate 018 distinguishes two statements:

\`\`\`text
the world has deterministic structure
\`\`\`

and:

\`\`\`text
the current learner can represent that structure
\`\`\`

For an XOR-like dependency, these are no longer equivalent.

If the gate validates as expected, it is direct evidence that pairwise temporal links
have reached a representational boundary for this class of contextual dependency.

## What it does not prove

The gate does not justify:

- semantic causal labels;
- hard-coded natural-language conjunctions;
- arbitrary Cartesian products of all observed patterns;
- replacing pairwise learning globally.

It only justifies investigating a sparse higher-order structural primitive for cases
where lower-order evidence demonstrably cannot encode the world dependency.

## Invariants

- the four physical combinations are deterministic;
- interaction physics is World-State-owned;
- interaction runtime contains no cognitive dependency;
- Water consequence uses the production distributed runtime;
- sensors use the production multimodal runtime;
- the corpus is balanced;
- every single signal/consequence pair has directional reliability near 0.5;
- every single context/consequence pair has directional reliability near 0.5;
- pairwise signal/context links do not create conjunction identities;
- RealitySlice creates no synthetic combined pattern;
- Memoria.ia cannot resolve the deterministic XOR outcome from a single pattern query;
- cognitive payloads contain no XOR or semantic world labels;
- result is deterministic.

## Next gate

If Gate 018 confirms the expected limit, Life Gate 019 should add the smallest possible
native higher-order structural candidate.

A suitable primitive would be an opaque, sparse, evidence-gated temporal context such
as:

\`\`\`text
{pattern A, pattern C} -> pattern P
\`\`\`

It should be created only when lower-order associations fail and repeated independent
RealitySlices support the same combination.

It must not be a semantic rule and must not generate the full combinatorial product of
all patterns.
