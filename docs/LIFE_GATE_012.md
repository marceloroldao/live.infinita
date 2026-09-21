# Life Gate 012 — World Runtime Physical Future Enumeration

## Objective

Remove the manually supplied future-band tuple from temporal prediction tests.

The World Runtime itself now previews the next environmental transition using the same
distributed physics and the same multimodal sensor sampler used for committed world
execution.

Only after that preview exists may Memoria.ia constrain the concrete future set.

## Order of authority

\`\`\`text
World State rules
    ↓
distributed environmental runtime
    ↓
next physical world preview
    ↓
multimodal sensor sampler
    ↓
physical sensor future set
    ↓
Memoria.ia temporal recall
    ↓
supported / unsupported continuation
\`\`\`

Memoria.ia is downstream of physics.

## Deterministic physics

The current distributed-water runtime is deterministic.

Therefore, for one sensor and one physical lookahead tick, the physically admissible
candidate set currently has cardinality one.

This is intentional.

Gate 012 does not introduce fake stochastic branches merely to create multiple
candidates. Future gates can add genuine world-declared uncertainty or exogenous
alternatives when such mechanics exist.

## World-owned preview policy

Life Gate 012 declares:

\`\`\`text
environmental_future_preview:
  runtime = distributed_environmental
  lookahead_ticks = 1
\`\`\`

The preview provider refuses to operate without this world-owned policy.

## Physical preview

\`environmental_future_runtime.py\` calls:

1. \`advance_distributed_environmental_agents(..., ticks=1)\`
2. \`sample_multimodal_sensor_frame(...)\`

Both functions already deep-copy their input.

The source world therefore remains unchanged.

The provider returns only coarse sensor future candidates containing:

- candidate ID;
- observer ID;
- sensor ID;
- committed band ID;
- target ID;
- region ID;
- source tick/version;
- preview physical tick;
- preview sensor tick;
- physical event ID;
- sensor frame ID.

Exact hidden environmental quantities are not sent to Memoria.ia.

## Preview/commit equivalence

The gate requires that:

\`\`\`text
preview(next physics + sensor)
==
commit(next physics + sensor)
\`\`\`

for all four Gate 007 channels:

\`\`\`text
presence  -> p1
intensity -> i1
trend     -> t2
flow      -> d1
\`\`\`

at the first distributed-water transition.

## Temporal prediction composition

\`environmental_temporal_prediction_runtime.py\` performs:

\`\`\`text
read current committed sensor band
    ↓
World Runtime physical preview
    ↓
physical future set
    ↓
Memoria.ia temporal candidate resolver
\`\`\`

The caller no longer supplies a future band tuple.

## Three-episode memory case

After three independent learned trajectories, Memoria.ia supports:

\`\`\`text
i2 -> i1
\`\`\`

A fresh world at \`i2\` physically previews \`i1\`.

Memoria.ia recognizes that concrete future and resolves it.

## Extra remembered future cannot expand physics

After four independent trajectories, temporal memory may support both:

\`\`\`text
i2 -> i1
i2 -> i0
\`\`\`

However, one physical lookahead tick from the current world still yields only:

\`\`\`text
i1
\`\`\`

The resolver receives a candidate set of size one.

The remembered \`i0\` continuation cannot be inserted into that set.

## Empty memory does not block physics

With no structural temporal observations:

- the World Runtime still previews \`i1\`;
- prediction assistance returns \`no-supported-world-continuation\`;
- committed physics still advances to \`i1\`.

Therefore memory recognition is optional assistance, not a prerequisite for world
evolution.

## Read-only boundary

Prediction assistance must not modify:

- source World State;
- structural temporal observation memory;
- causal intervention memory.

## Invariants

- future candidates originate from World Runtime physics;
- no future band is supplied manually to Memoria.ia;
- preview uses the same physics implementation as commit;
- preview uses the same sensor implementation as commit;
- preview equals commit for the tested deterministic world;
- source world remains unchanged;
- temporal memory cannot expand the physical candidate set;
- empty memory does not alter physical evolution;
- hidden exact environmental quantities do not enter Memoria.ia;
- prediction is deterministic.

## Next gate

Life Gate 013 should introduce a **genuine branching physical possibility** owned by the
World State, not by memory.

Examples include a world-declared external perturbation, controllable gate/valve state,
or another environmental agent whose state makes more than one next transition
physically admissible.

Only then should Memoria.ia be tested against a physical candidate set larger than one.
