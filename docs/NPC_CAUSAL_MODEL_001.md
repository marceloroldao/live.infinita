# NPC Causal Model 001

## Purpose

Add a deterministic, evidence-weighted causal-hypothesis layer above descriptive beliefs without converting temporal correlation into a fact.

The first baseline asks a narrow question:

```text
when the world period changes,
does environmental danger repeatedly change in a consistent direction?
```

The runtime records this as a provisional relation, not as proven causality.

## Separation of cognitive layers

```text
Episode
  concrete event: what happened

Belief
  descriptive regularity: what seems common in a context

Causal hypothesis
  provisional relation: what change tends to precede another change

Statistical experience
  accumulated operational outcome/cost evidence
```

These layers remain distinct. A causal hypothesis never rewrites an episode or turns a belief into an immutable fact.

## Observation boundary

`WorldTickRunner` captures an environmental snapshot immediately after the logical clock advances and before scheduled world events run.

It captures a second snapshot after:

1. `WorldEventScheduler` scheduled events;
2. `ConditionalEventScheduler` state reactions.

Only then does `NpcCausalModel` inspect the transition. NPC need dynamics execute afterward.

This creates a deterministic causal-observation window:

```text
world before scheduled events
  -> scheduled mutation(s)
  -> conditional reaction(s)
  -> world after reactions
  -> provisional causal observation
  -> NPC need dynamics
```

The causal model has no mutation authority.

## First hypothesis family

The first schema is:

```text
cause:
  environment_period_transition
  from: day|night|...
  to: night|day|...

effect:
  metric: environment.danger_level
  expected_direction: increase|decrease|stable
```

For the Nov baseline:

```text
day -> night
candidate effect: danger_level increases

night -> day
candidate effect: danger_level decreases
```

The expectation is only a hypothesis template. Every actual transition is classified as support, counterevidence, or neutral evidence from the measured delta.

## Evidence model

Each hypothesis stores:

```text
count
support_count
counter_count
neutral_count
mean_effect_delta
confidence
last_observation_id
last_logical_tick
evidence[]
status = provisional
```

Evidence rows preserve:

- logical tick;
- before/after environmental snapshots;
- measured delta;
- observed direction;
- source scheduled/conditional event references.

Observation IDs are idempotent, so replay or duplicate processing cannot reinforce a relation twice.

## Confidence

Confidence deliberately requires both repeated evidence and directional consistency.

```text
evidence_strength = count / (count + prior_strength)
directional_balance = abs(support_count - counter_count) / count
confidence = evidence_strength * directional_balance
```

Default `prior_strength` is `4.0`.

Consequences:

- one observation cannot create high confidence;
- repeated consistent observations increase confidence;
- balanced support/counterevidence drives confidence toward zero;
- the hypothesis remains `provisional` even with high confidence.

## Counterevidence

Suppose repeated observations initially show:

```text
day -> night
risk +0.30
risk +0.35
risk +0.25
```

Then later:

```text
day -> night
risk -0.20
```

The negative observation is not discarded. It increments `counter_count`, updates the online mean effect and reduces directional confidence.

This follows the Memoria.ia epistemic direction: facts/evidence are not imposed rigidly at ingest; competing evidence remains present and reinforcement over time determines confidence.

## Scope of v1

This version deliberately does **not**:

- infer arbitrary causal graphs;
- use an LLM;
- use embeddings;
- claim interventions or counterfactual proof;
- modify world state;
- directly change NPC strategy choice.

It only builds auditable provisional hypotheses from deterministic transitions.

## Persistence

State is persisted under:

```text
npc-causal-hypotheses.json
```

Rebuilding the cognitive stack with the same data directory preserves hypotheses and processed observation IDs.

## Nov scenario

The autonomous Nov scenario supplies the first real causal observations:

```text
tick 12:
  day -> night
  danger 0.05 -> 0.35
  hypothesis support: night transition precedes increased danger

 tick 24:
  night -> day
  danger 0.35 -> 0.05
  hypothesis support: day transition precedes decreased danger
```

The same tick may also light or extinguish the campfire through conditional reactions, and source-event provenance is attached to the causal observation.

## Next stage

Only after this baseline is stable should causal hypotheses influence decisions. The intended rule is conservative:

```text
empirical strategy evidence > descriptive belief > causal hypothesis
```

A causal hypothesis should initially act only as a bounded prior when direct empirical evidence is absent, never as autonomous authority.
