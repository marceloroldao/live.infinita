# Life Gate 010 — Memoria.ia Structural Temporal Observation

## Objective

Complete the first controlled handoff from admitted temporal evidence into Memoria.ia
V2 without reusing causal intervention memory.

The gate introduces a dedicated additive memory for passive temporal structure.

## Cross-repo path

```text
Live.infinita
  ↓
sensor trajectory
  ↓
RealitySlice
  ↓
bit.analyze TemporalAssociator
  ↓
Life Gate 009 Evidence Selector
  ↓
TemporalEvidenceCandidate
  ↓
Life Gate 010 adapter
  ↓
Memoria.ia StructuralTemporalObservationMemory
```

## Memoria.ia component

Repository:

`marceloroldao/memoria.ia`

Branch lineage:

`experiment/address-trajectory-v2`

Validated commit:

`33599674bf9dbc62063bc96b0426c565f5e9f77d`

Module:

`src/memoria_resolutiva/structural_temporal_observation_v2.py`

The component is separate from `InterventionConsequenceMemory`.

## Why a separate memory is required

The existing causal V2 memory records:

```text
state -> intervention -> consequence
```

A passive temporal association has no actual intervention.

Gate 010 therefore does **not** fabricate an intervention such as
`observe_temporal_relation`.

## Observation contract

An admitted candidate is stored as:

```text
opaque pattern A
opaque pattern B
orientation
upstream evidence metrics
supporting RealitySlice IDs
supporting frame IDs
provenance
```

No semantic predicate is generated.

## Idempotency

Replaying the same exact candidate/provenance bundle returns the existing observation
rather than creating new independent support.

## Reinforcement by provenance union

If one observation carries slices:

```text
1, 2, 3
```

and a later expanded observation carries:

```text
1, 2, 3, 4
```

support becomes 4.

The memory does not sum 3 + 4.

## Competing evidence

Suppose one orientation has independent support:

```text
A -> B : slices 1, 2, 3
```

and later weak contrary evidence appears:

```text
B -> A : slice 4
```

The contrary observation is preserved but does not erase the supported history.

If the contrary orientation later reaches independent support:

```text
B -> A : slices 4, 5, 6
```

the resolution becomes ambiguous:

```text
A -> B supported
B -> A supported

resolved = false
ambiguous = true
```

No winner is selected.

## Evidence metrics

The Memoria.ia observation stores:

- rho;
- selectivity;
- temporal stability;
- evidence score;
- orientation confidence;
- mean dt;
- dt variance.

These are audit fields.

They are not converted into a truth score and are not used to silently rank competing
orientations.

## Causal boundary

Gate 010 explicitly verifies that ingesting passive temporal evidence does not modify:

- `InterventionConsequenceMemory`;
- situated causal regimes.

Thus:

```text
passive temporal observation != causal episode
```

## Semantic boundary

The stored observation does not contain:

- water;
- flow;
- intensity;
- cause;
- fact;
- truth;
- law.

Only opaque temporal pattern addresses are stored.

## Current limitation

The observation memory currently exists in-process and supports snapshot/restore.

Gate 010 does not yet persist it into the BDR durable store and does not yet expose it
to the server API.

## Next gate

Life Gate 011 should test **temporal structural recall and prediction assistance**
without promoting observations to causal facts.

A useful first target is:

- given current opaque pattern A;
- retrieve supported temporal continuations;
- return all supported orientations/candidates;
- preserve ambiguity;
- never manufacture a continuation absent from the World Runtime.
