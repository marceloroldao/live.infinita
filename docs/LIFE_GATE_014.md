# Life Gate 014 — Endogenous Multi-Agent Environmental Causality

## Objective

Replace the abstract external control of Life Gate 013 with another autonomous world
agent.

The second agent is **Wind**.

Wind owns its own internal phase trajectory. Its current phase produces an
environmental action that changes the availability of the Water route
\`spring_channel\`.

Memoria.ia does not choose the Wind action.

## Authority chain

\`\`\`text
Wind internal state
    ↓
Wind autonomous action
    ↓
route availability
    ↓
distributed Water physics
    ↓
Nov sensor frame
    ↓
bit.analyze / Memoria.ia
\`\`\`

The causal influence therefore exists in World Runtime before cognition observes it.

## Wind agent

Entity:

\`wind_01\`

Class:

\`environmental_agent\`

Type:

\`wind\`

The agent has an \`environmental_state.phase_id\`.

The world declares the phase graph through
\`environmental_influence_agents\`.

Current Gate 014 cycle:

\`\`\`text
w_gust_a
  -> action wind_open_channel
  -> w_gust_b

w_gust_b
  -> action wind_open_channel
  -> w_lull_a

w_lull_a
  -> action wind_close_channel
  -> w_lull_b

w_lull_b
  -> action wind_close_channel
  -> w_gust_a
\`\`\`

Each regime persists for two influence steps.

This persistence is physical/world-owned. It is not a temporal-learning threshold
adjustment.

## Why two-step persistence exists

A one-step alternation between gust and lull would cause the same observable relation
to occur at materially different temporal offsets inside the three-frame RealitySlice.

That would correctly reduce temporal stability in bit.analyze.

Rather than weakening the evidence gate, Gate 014 gives Wind a world-state persistence
consistent with a real environmental regime.

## Influence runtime

Module:

\`environmental_influence_agent_runtime.py\`

\`advance_environmental_influence_agents()\`:

1. reads the agent's current phase;
2. selects the action declared for that phase;
3. applies the route override;
4. records the action in Event/Delta history;
5. advances the agent to its next phase.

No observer action, Memoria.ia state, or external branch selector is consulted.

## Coupled environment

Module:

\`multiagent_environment_runtime.py\`

One coupled step is:

\`\`\`text
Wind influence tick
    ↓
Water distributed tick
    ↓
multimodal sensor tick
\`\`\`

The tick ordering itself is validated.

## Same observer state, different world causality

Two fresh worlds can present Nov with the same current observable flow state:

\`\`\`text
s_flow = d0
\`\`\`

and the same local structural observer projection.

However:

### Wind in gust regime

\`\`\`text
Wind phase w_gust_a
    ↓
wind_open_channel
    ↓
spring_channel available
    ↓
Water
    ↓
next s_flow = d1
\`\`\`

### Wind in lull regime

\`\`\`text
Wind phase w_lull_a
    ↓
wind_close_channel
    ↓
spring_channel unavailable
    ↓
Water
    ↓
next s_flow = d2
\`\`\`

Thus identical current observer state does not imply identical full world state.

## Physical ambiguity from Gate 013 is contextualized

Gate 013 represented both valve states as externally admissible branches.

Gate 014 adds causal state that exists inside the world.

Given the actual Wind phase, World Runtime produces one next physical continuation.

Therefore:

\`\`\`text
Gate 013:
missing causal state -> two admissible physical branches

Gate 014:
Wind state present -> one agent-conditioned physical future
\`\`\`

This collapse happens before Memoria.ia.

## Learning both histories

Training episodes can include both regimes:

\`\`\`text
d0 -> d1    under gust
d0 -> d2    under lull
\`\`\`

Temporal memory may support both structural continuations.

A fresh world with Wind in gust produces only the \`d1\` physical candidate.

A fresh world with Wind in lull produces only the \`d2\` physical candidate.

Memoria.ia recognizes the world-resolved candidate rather than choosing between the two
histories.

## Memory cannot override another agent

If temporal memory has learned only the gust/open history, but the current world has
Wind in lull:

\`\`\`text
World Runtime future = d2
Memoria.ia = no-supported-world-continuation
\`\`\`

The autonomous coupled commit still reaches \`d2\`.

Therefore failure to recognize a future does not block or rewrite another agent's
causal action.

## Semantic boundary

The Memoria.ia temporal resolution receives only opaque temporal pattern addresses and
candidate IDs.

It does not receive:

- Wind;
- gust/lull labels;
- open/close action names;
- exact Water distribution;
- raw sensor values.

The World Runtime candidate retains causal provenance for audit, while the cognitive
resolution remains pre-semantic.

## Invariants

- Wind is an autonomous world agent;
- Wind action comes from its own current phase;
- Wind phase evolves without Memoria.ia;
- Wind modifies a physical Water route;
- Water evolves after the Wind action;
- sensors sample after Water evolves;
- same Nov-observable state can coexist with different hidden causal world state;
- full world state resolves the physical future before memory;
- memory can recognize but cannot override Wind;
- temporal prediction is read-only;
- hidden exact Water state remains outside Memoria.ia;
- result is deterministic.

## Next gate

Life Gate 015 should make **Nov able to discover the hidden causal agent indirectly**.

Nov should not receive a hard-coded statement such as "Wind caused Water to change".

Instead, add an independent Wind-related sensory channel or structural trace, then let
bit.analyze discover temporal co-occurrence across:

\`\`\`text
Wind pattern
    ↓ temporal relation
Water pattern
\`\`\`

Repeated experience should determine whether a stable cross-agent association emerges.
