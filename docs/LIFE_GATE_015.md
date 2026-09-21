# Life Gate 015 — Emergent Cross-Agent Temporal Association

## Objective

Let Nov acquire an independent structural signal related to the autonomous Wind agent
and allow bit.analyze to discover temporal structure between that signal and Water
consequences.

No semantic relation such as:

\`\`\`text
Wind causes Water
\`\`\`

is created.

The only cross-agent relationship available to cognition must emerge from repeated
RealitySlices.

## Independent agent signal

Gate 015 adds a generic multimodal sensor kind:

\`component_enum\`

It reads one world-owned entity component field and maps exact world values to opaque
bands.

Scenario channel:

\`\`\`text
sensor_id: s_agent_signal_01
target: wind_01
source_component: environmental_state
source_field: phase_id
kind: component_enum
\`\`\`

World-only mapping:

\`\`\`text
w_gust_a -> a0
w_gust_b -> a0
w_lull_a -> a1
w_lull_b -> a1
\`\`\`

The exact phase remains inside World State sensor provenance.

The public synchronized sensor event exposes only:

\`\`\`text
s_agent_signal_01 / a0
\`\`\`

or:

\`\`\`text
s_agent_signal_01 / a1
\`\`\`

## Selective sensor sampling

\`sample_multimodal_sensor_frame()\` now accepts an optional \`sensor_ids\` filter.

This allows separate temporal frames to be created for independent observations rather
than forcing every available channel into every frame.

Existing callers without a filter retain the previous all-channel behavior.

## RealitySlice trajectory

Each Gate 015 learning episode contains exactly three sensor frames.

### Gust regime

\`\`\`text
frame 0: Water flow d0
frame 1: agent signal a0
          ↓
        Wind acts
          ↓
        Water evolves
frame 2: Water flow d1
\`\`\`

### Lull regime

\`\`\`text
frame 0: Water flow d0
frame 1: agent signal a1
          ↓
        Wind acts
          ↓
        Water evolves
frame 2: Water flow d2
\`\`\`

The RealitySlice bridge receives only opaque sensor pattern IDs.

## Cross-agent learning

Balanced repeated experience uses independent episodes:

\`\`\`text
4 gust episodes
4 lull episodes
\`\`\`

Expected learned structural pairs:

\`\`\`text
a0 -> d1
a1 -> d2
\`\`\`

Pairs that never occurred must not appear:

\`\`\`text
a0 -> d2
a1 -> d1
\`\`\`

Admission still uses the existing Gate 009 evidence policy:

- independent repetition;
- rho;
- selectivity;
- temporal stability;
- evidence score;
- direction confidence.

No cross-agent exception is added.

## One episode remains insufficient

A single \`a0 -> d1\` episode creates a temporal link in bit.analyze but does not cross
the evidence gate.

This preserves the rule that one observation is not a learned structural relation.

## Memoria.ia recall

After admitted temporal candidates are ingested into
\`StructuralTemporalObservationMemory\`, recall from the opaque agent signal can expose
the matching supported continuation.

For \`a0\`:

\`\`\`text
after_query contains d1
after_query does not contain d2
\`\`\`

For \`a1\`:

\`\`\`text
after_query contains d2
after_query does not contain d1
\`\`\`

Memoria.ia still stores only opaque temporal pattern addresses.

## Direction is learned from timing

Gate 015 includes an adversarial timing test.

The physical world is unchanged, but the agent signal is sampled after the Water
consequence:

\`\`\`text
d0
d1
a0
\`\`\`

The recalled relationship between \`a0\` and \`d1\` becomes:

\`\`\`text
before_query
\`\`\`

instead of:

\`\`\`text
after_query
\`\`\`

Therefore temporal direction is determined by observed ordering, not by a hard-coded
"Wind before Water" rule.

## Provenance

A cross-agent candidate admitted after four independent episodes preserves:

\`\`\`text
4 independent RealitySlices
12 originating sensor frames
\`\`\`

This remains auditable across the full path.

## Semantic boundary

The Memoria.ia snapshot and transport payload contain no:

- Wind label;
- gust/lull label;
- Water label;
- flow label;
- open/close action label;
- causal predicate.

The world and sensor runtimes know their targets.

The temporal learner and memory receive opaque pattern identities and evidence only.

## Invariants

- the Wind-related signal is an independent sensor channel;
- exact Wind phase stays in World State;
- public sensor events expose only opaque bands;
- Water and agent signal occupy distinct temporal frames;
- one episode is insufficient;
- repeated episodes can admit a cross-agent structural relation;
- unobserved crossed pairs do not appear;
- direction follows observation timing;
- Memoria.ia recall preserves the learned direction;
- no semantic causal edge is inserted;
- provenance remains independent and auditable;
- existing multisensor behavior remains backward compatible;
- result is deterministic.

## Next gate

Life Gate 016 should test **counterfactual discrimination without causal labels**.

A useful experiment is to hold the agent signal constant while changing another world
condition that breaks the usual Water consequence.

If \`a0\` sometimes precedes \`d1\` and sometimes does not because a third physical
condition intervenes, the temporal association should lose selectivity/stability or
remain explicitly contextual rather than being promoted to universal causality.

That would distinguish repeated temporal association from stronger causal evidence.
