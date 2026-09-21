# Life Gate 011 — Structural Temporal Recall and Prediction Assistance

## Objective

Use the structural temporal observations learned through Life Gates 008–010 to assist
prediction without giving Memoria.ia authority to invent the world.

The central contract is:

\`\`\`text
Memoria.ia remembers possible temporal structure
World Runtime supplies concrete possible futures
resolver intersects both sets
\`\`\`

## Cross-repo path

\`\`\`text
Live.infinita
  ↓
sensor trajectory
  ↓
RealitySlice
  ↓
bit.analyze
  ↓
Evidence Selector
  ↓
StructuralTemporalObservationMemory
  ↓
Structural Temporal Recall
  ↓
intersection with World Runtime candidates
\`\`\`

## Memoria.ia implementation

Repository:

\`marceloroldao/memoria.ia\`

Branch lineage:

\`experiment/address-trajectory-v2\`

Gate commit:

\`438c273d98479a550e2162964deecf737e0a5891\`

Module:

\`src/memoria_resolutiva/structural_temporal_recall_v2.py\`

## Live adapter

\`temporal_prediction_memoria_adapter.py\` converts world-offered sensor futures into
the same opaque temporal pattern addresses used by RealitySlice.

Input to the adapter is explicit:

\`\`\`text
(candidate_id, sensor_id, band_id)
\`\`\`

The adapter does not discover alternatives.

## Three-episode case

The Gate 009 selector admits the nearer temporal transition:

\`\`\`text
i2(frame 0) -> i1(frame 1)
\`\`\`

while the farther:

\`\`\`text
i2(frame 0) -> i0(frame 2)
\`\`\`

remains below the evidence gate.

If World Runtime supplies:

\`\`\`text
world_i1 -> i1
world_i0 -> i0
\`\`\`

the resolver can select only \`world_i1\`.

This is not creation of \`i1\`; \`world_i1\` already existed in the world candidate set.

## Missing world future

If memory supports \`i1\`, but World Runtime supplies only \`i0\`:

\`\`\`text
result:
no-supported-world-continuation
\`\`\`

Memoria.ia cannot insert \`i1\` into the candidate set.

## Four-episode case

After enough independent trajectories, both the nearer and farther transitions may
cross the upstream evidence gate.

Even when:

\`\`\`text
rho(i2 -> i1) > rho(i2 -> i0)
\`\`\`

if World Runtime supplies both concrete futures, the result is:

\`\`\`text
resolved = false
ambiguous = true
reason = multiple-supported-world-continuations
\`\`\`

The higher rho is not used as a hidden winner-selection score.

## Contested direction

If memory independently supports both temporal orientations for the same pair, a
single concrete world future remains contested.

The resolver preserves ambiguity rather than selecting the orientation with the larger
metric value.

## Causal boundary

Prediction assistance remains separate from:

- \`InterventionConsequenceMemory\`;
- situated causal regimes.

Temporal recall is read-only.

## Invariants

- recall can expose remembered temporal structure;
- only supported structure is recalled;
- world candidates are externally supplied;
- memory cannot expand the candidate set;
- reverse temporal evidence is not treated as a future;
- simultaneous evidence is not treated as a future;
- multiple valid futures preserve ambiguity;
- contested direction preserves ambiguity;
- rho does not rank concrete futures;
- recall does not mutate memory;
- causal memory remains separate;
- output is deterministic.

## Next gate

Life Gate 012 should connect this prediction-assistance contract to an actual
World Runtime environmental transition proposal boundary.

The useful test is no longer a manually supplied tuple of future sensor bands. The
World Runtime itself should enumerate physically admissible next environmental sensor
states, then Memoria.ia may constrain that set without controlling the physics.
