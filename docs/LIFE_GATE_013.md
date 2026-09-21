# Life Gate 013 — Genuine World-Owned Physical Branching

## Objective

Introduce the first genuinely branching physical future set in Live.infinita.

The branching source belongs to World State and World Runtime, not to Memoria.ia.

The world contains an external environmental control: a physical valve attached to the
\`spring_channel\` route.

Before the external control input is resolved, two next control states are physically
admissible:

\`\`\`text
v_channel_open
v_channel_closed
\`\`\`

Each state is applied on an isolated world copy, then evaluated through the real
distributed environmental physics and the real multimodal sensor sampler.

## Physical effect

At the initial spring state:

\`\`\`text
Water at spring = 100 units
\`\`\`

### Branch A — channel open

Both spring routes remain available:

\`\`\`text
spring_channel capacity 40
spring_hollow  capacity 30
\`\`\`

The next observed flow channel is:

\`\`\`text
s_flow = d1
\`\`\`

The next local intensity is:

\`\`\`text
s_intensity = i1
\`\`\`

### Branch B — channel closed

\`spring_channel\` becomes unavailable and only \`spring_hollow\` can transfer water.

The next observed flow channel is:

\`\`\`text
s_flow = d2
\`\`\`

The next local intensity is:

\`\`\`text
s_intensity = i2
\`\`\`

Thus the branching is not synthetic sensor noise. It comes from a world-owned physical
route state that changes the distributed-water calculation.

## Branching control contract

Scenario:

\`scenario_life_gate_013.py\`

Runtime:

\`environmental_branching_runtime.py\`

World rule:

\`\`\`text
environmental_branching_control:
  control_id: spring_channel_valve
  entity_id: valve_spring_channel_01
  runtime: distributed_environmental
  lookahead_ticks: 1
  admissible_next_states:
    - v_channel_open
    - v_channel_closed
\`\`\`

Each state contains explicit route overrides.

## Preview authority

\`enumerate_branching_distributed_sensor_candidates()\`:

1. reads admissible branch states from World State;
2. applies each branch only to an internal copy;
3. runs the real distributed physics;
4. samples the result using the real multimodal sensor runtime;
5. returns all physical sensor futures.

Memoria.ia is not involved in steps 1–5.

## Commit authority

\`commit_branching_environmental_state()\` requires an explicit external
\`control_state_id\`.

It does not accept a Memoria.ia resolution object and does not ask memory which branch
to choose.

A real external choice is recorded in the same authoritative physical Event/Delta:

- control ID;
- selected control state;
- control entity;
- route override;
- provenance.

Therefore an actual branch choice is auditable.

## Memoria.ia integration

\`environmental_branching_temporal_prediction_runtime.py\` executes:

\`\`\`text
current sensor state
    ↓
World Runtime branch enumeration
    ↓
physical future set [A, B]
    ↓
Memoria.ia temporal recall
    ↓
recognized / ambiguous / unsupported
\`\`\`

## Memory trained only on open branch

Three independent open-valve trajectories support:

\`\`\`text
d0 -> d1
\`\`\`

The fresh world still produces two physical futures:

\`\`\`text
d1 via v_channel_open
d2 via v_channel_closed
\`\`\`

Memoria.ia may recognize \`d1\` as the only supported continuation.

However, an external caller can still commit:

\`\`\`text
v_channel_closed
\`\`\`

and physics produces \`d2\`.

Recognition does not equal physical control.

## Memory trained on both branches

Three independent open trajectories plus three independent closed trajectories support:

\`\`\`text
d0 -> d1
d0 -> d2
\`\`\`

The same fresh world offers both physical futures.

The expected resolution is:

\`\`\`text
resolved = false
ambiguous = true
reason = multiple-supported-world-continuations
\`\`\`

No branch is selected.

## Unequal history

The gate also tests more experience for one branch than the other.

As long as both branches independently pass the structural support gates, Memoria.ia
does not use the larger rho/evidence history to override legitimate physical ambiguity.

This preserves the Gate 011 rule:

\`\`\`text
supported physical possibility != ranked winner
\`\`\`

## Empty memory

With no temporal observations:

- World Runtime still generates both physical futures;
- Memoria.ia resolves neither;
- the branch set remains intact.

## Hidden physical variables

The Memoria.ia resolution does not receive:

- \`by_region\`;
- \`initial_total\`;
- \`evaporated_total\`;
- \`environmental_distribution\`;
- \`raw_value\`;
- \`source_value\`.

Only opaque sensor pattern addresses enter temporal recall.

## Invariants

- at least two next physical states are genuinely admissible;
- branch states are World-State-owned;
- branch enumeration is read-only;
- branch enumeration does not consult Memoria.ia;
- every branch runs the same production physics;
- every branch runs the same production sensor sampler;
- actual branch commit requires explicit external state;
- actual branch choice is recorded in Event/Delta provenance;
- memory cannot actuate the valve;
- memory cannot add a physical branch;
- memory cannot delete a physical branch;
- multiple supported physical futures preserve ambiguity;
- stronger history does not silently choose a winner;
- empty memory does not change physical admissibility;
- hidden physical quantities remain outside Memoria.ia;
- result is deterministic.

## Next gate

Life Gate 014 should make the external branching condition itself arise from another
living world agent rather than an abstract unresolved external control.

A strong next case is a second environmental agent whose action changes the valve or
route state. The physical future set would then depend on another agent's independently
evolving state, moving from exogenous branching toward multi-agent world causality.
