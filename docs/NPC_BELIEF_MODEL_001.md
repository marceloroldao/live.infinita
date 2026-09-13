# NPC Belief Model 001

## Purpose

Add a deterministic internal world model above episodic memory without converting observations into rigid facts.

A belief is an evidence-weighted hypothesis. It can strengthen, weaken or remain ambiguous as new episodes arrive.

## Current belief type

The first belief family is contextual environmental risk:

```text
NPC + region + period + weather -> observed risk distribution
```

Example:

```text
Nov + deep_forest + night + clear
```

may accumulate observations such as:

```text
0.80 risk  -> supporting evidence
0.75 risk  -> supporting evidence
0.10 risk  -> counterevidence
```

The resulting belief is not `deep_forest_at_night_is_dangerous = true`.

It stores:

```text
count
mean_risk
support_count
counter_count
neutral_count
confidence
evidence_episode_ids
last_episode_id
last_logical_tick
```

## Confidence

Confidence grows with repeated independent episode observations:

```text
confidence = count / (count + prior_strength)
```

The default `prior_strength` is 3.0. A single observation therefore cannot create high confidence.

## Supporting and counter evidence

For the first risk belief:

```text
observed_risk >= 0.60 -> support
observed_risk <= 0.25 -> counterevidence
otherwise             -> neutral evidence
```

These counters remain visible even when the running mean becomes high or low. Contradictory experience is not discarded.

## Provenance

Beliefs are derived only from persisted `npc_episode_v1` records.

The same `episode_id` cannot reinforce a belief twice. `processed_episode_ids` makes belief derivation idempotent across restart or replay.

The belief keeps bounded recent episode references for auditability while the episodic memory remains the source of the full concrete history.

## Experienced region

The decision context may say where the NPC was when an intention was formed. This is not necessarily where the resulting experience happened.

When an episode has a `target_entity_id`, `NpcBeliefModel` resolves that entity through the authoritative cold store and uses the target's current region as the experienced region.

Therefore an episode that starts in `clearing` and reaches `ancient_tree` can reinforce:

```text
Nov + deep_forest + night
```

rather than incorrectly reinforcing `clearing + night`.

## Decision influence

`NpcStrategyValue` can consume a contextual risk belief while it is still using heuristic cost estimates.

The blend is bounded:

```text
belief_blend = belief_weight * belief_confidence
```

with default:

```text
belief_weight = 0.25
```

Then:

```text
effective_risk =
    (1 - belief_blend) * heuristic_risk
  + belief_blend       * believed_mean_risk
```

If mature empirical strategy-cost evidence exists, the empirical risk remains authoritative for that decision and the belief blend is zero. This prevents the same historical experience from being counted twice through both aggregate strategy statistics and derived belief.

Episodic bias remains a separate bounded signal. Exploration ordering also remains unchanged.

## Epistemic rule

The intended ordering is:

```text
concrete episode
    -> evidence
    -> provisional belief
    -> repeated support / counterevidence
    -> changing confidence
    -> bounded decision influence
```

Not:

```text
single observation -> permanent fact
```

This matches the broader Memoria.ia direction that facts/evidence should emerge from converging observations and reinforcement rather than being imposed rigidly at ingestion time.

## Persistence

Beliefs are stored in:

```text
npc-beliefs.json
```

They survive cognitive-stack rebuilds and remain separate from:

```text
npc-episodes.jsonl              concrete experiences
npc-need-learning.json          target reward aggregates
npc-strategy-experience.json    strategy cost/outcome aggregates
```

## External Memoria.ia boundary

This is a local deterministic baseline. A future adapter may export episodes and/or derived beliefs to Memoria.ia.

The autonomous world must not depend on the Memoria.ia server being reachable in order to advance logical time or make bounded deterministic decisions.
