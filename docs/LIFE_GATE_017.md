# Life Gate 017 — Context as an Autonomous Trajectory

## Objective

Replace Gate 016's per-episode static context with a world process that evolves through
its own persistent trajectory.

The context is no longer selected by the test through a \`context_state_id\` argument.

Every Gate 017 world starts in the same state:

\`\`\`text
barrier_01.phase = b_clear
\`\`\`

The barrier then evolves autonomously:

\`\`\`text
b_clear
  -> barrier_allow_channel
  -> b_blocked

b_blocked
  -> barrier_block_channel
  -> b_clear
\`\`\`

No Memoria.ia state, observer action, or external context selector participates.

## Three independently evolving parts

The causal order for one physical step is:

\`\`\`text
Wind process
    ↓
context process (barrier_01)
    ↓
distributed Water
    ↓
sensor sampling
\`\`\`

Each stage writes its own authoritative Event/Delta.

Module:

\`contextual_multiagent_environment_runtime.py\`

## One world, two contexts

Wind starts in \`w_gust_a\` and persists in the gust family for two steps:

\`\`\`text
step 1: w_gust_a -> w_gust_b
step 2: w_gust_b -> w_lull_a
\`\`\`

The opaque Wind signal is therefore \`a0\` in both steps.

The barrier starts in \`b_clear\` and alternates each step:

\`\`\`text
step 1: b_clear   -> b_blocked
step 2: b_blocked -> b_clear
\`\`\`

The opaque context signal becomes:

\`\`\`text
step 1: c0
step 2: c1
\`\`\`

After the first Water redistribution, Spring retains only 20 units. On the second
Water tick, 10 units evaporate and the remaining 10 satisfy Spring retention, leaving
no mobile quantity at Spring. Therefore the blocked-context flow observation is
`d0` (no dominant transfer), not the static-world `d2` seen in Gate 016.

The resulting Water trajectory in the same world is:

\`\`\`text
d0
  ↓
a0 + c0
  ↓
d1
  ↓
a0 + c1
  ↓
d0
\`\`\`

No per-episode context selection is used.

## RealitySlices

The first four-frame window is:

\`\`\`text
d0 -> a0 -> c0 -> d1
\`\`\`

The second four-frame window, from the same world trajectory, is:

\`\`\`text
d1 -> a0 -> c1 -> d0
\`\`\`

This is intentionally richer than Gate 016.

The prior consequence \`d1\` becomes the next state's starting observation before
\`c1\`.

Therefore a pair such as \`d1/c1\` may exist structurally, but its temporal direction
must remain correct:

\`\`\`text
d1 -> c1
\`\`\`

It must not become a false \`c1 -> d1\` future.

## Universal Wind relation remains rejected

Across repeated two-step episodes, \`a0\` occurs in both contexts.

Its Water consequences differ:

\`\`\`text
a0 ... d1
a0 ... d0
\`\`\`

The directional-reliability policy introduced in Gate 016 prevents either consequence
from becoming a universal continuation of \`a0\`.

Memoria.ia recall from \`a0\` must not expose \`d1\` or \`d2\` as a supported
\`after_query\` continuation.

## Context-specific future remains valid

The evolving process still produces reliable context-specific structure:

\`\`\`text
c0 -> d1
c1 -> d0
\`\`\`

These relations can remain above the evidence gate because each context signal is
consistently followed by its matching physical consequence.

## Learning the context trajectory itself

Gate 017 also isolates the context process as its own observed trajectory:

\`\`\`text
c0
  ↓ autonomous barrier transition
c1
\`\`\`

Four independent episodes are ingested as separate RealitySlices.

Expected result:

\`\`\`text
c0 -> c1
\`\`\`

with:

- four independent slice supports;
- high direction confidence;
- high directional reliability;
- admission through the same generic evidence selector;
- Memoria.ia recall of \`c1\` as an \`after_query\` continuation from \`c0\`.

No special "context transition" semantic edge is created.

## Provenance

An admitted \`c0 -> c1\` trajectory candidate retains:

\`\`\`text
4 independent RealitySlices
8 originating sensor frames
\`\`\`

This keeps the learned context trajectory auditable.

## Semantic boundary

The temporal candidate and Memoria.ia snapshot do not contain:

- barrier;
- clear/blocked labels;
- process labels;
- Wind;
- Water;
- flow;
- cause/causes.

The world runtime knows the process identity and physical effect.

The cognitive layers receive opaque temporal pattern identities.

## Architectural result

Gate 016:

\`\`\`text
context supplied per episode
\`\`\`

Gate 017:

\`\`\`text
context evolves inside the world
    ↓
context is sensed
    ↓
context trajectory is learned
    ↓
context-specific consequences remain distinguishable
\`\`\`

For this deterministic experiment, overlapping pairwise temporal structure is
sufficient to preserve:

- the context trajectory;
- the context-specific Water continuation;
- rejection of the uncontextualized Wind continuation.

A native higher-order conjunction is not yet required by this gate.

## Next gate

Life Gate 018 should stress this pairwise representation with a case where neither
single context pattern is sufficient.

A useful test is an XOR-like physical condition:

\`\`\`text
signal A + context X -> consequence P
signal A + context Y -> consequence Q
signal B + context X -> consequence Q
signal B + context Y -> consequence P
\`\`\`

If pairwise associations cannot represent that dependency without ambiguity, that
would provide concrete evidence for a native multi-pattern contextual association
primitive rather than adding one prematurely.
