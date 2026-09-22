# Conditional World Events 002

## Goal

Extend deterministic conditional world events with temporal persistence and typed composition while preserving bounded local cost and Mutation Gate authorization.

## New predicates

### all

All child predicates must be true.

Example: rain AND night.

```json
{
  "kind": "all",
  "conditions": [
    {"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
    {"kind": "world_equals", "path": ["environment", "weather"], "value": "rain"}
  ]
}
```

### any

At least one child predicate must be true.

### not

Negates one typed child predicate.

### nobody_near_entity

Checks a bounded local region around an anchor entity. In cold-store mode only the anchor's region bucket is loaded; the universe is never globally scanned.

```json
{
  "kind": "nobody_near_entity",
  "anchor_entity_id": "fire_01",
  "radius": 8,
  "entity_types": ["human"]
}
```

Optional `exclude_entity_ids` may explicitly remove entities from the aggregate.

## Temporal sustain

Any top-level condition may declare `sustain_ticks`.

```json
{
  "kind": "entity_in_region",
  "entity_id": "nov",
  "region_id": "village",
  "sustain_ticks": 20
}
```

The raw predicate must remain continuously true for 20 logical ticks. If it becomes false, `true_since_tick` resets and counting restarts on the next false -> true transition.

No wall-clock timestamps are used for semantic timing.

## Example: unattended fire

```json
{
  "kind": "nobody_near_entity",
  "anchor_entity_id": "fire_01",
  "radius": 8,
  "entity_types": ["human"],
  "sustain_ticks": 80
}
```

Effect:

```json
{"op":"set","entity_id":"fire_01","path":["properties","lit"],"value":false}
```

Meaning: if no human is within radius 8 of the fire for 80 consecutive world ticks, turn the fire off.

## Example: weather composition

Condition:

rain AND night.

Effect:

reduce `environment.visibility`.

This is deterministic, requires no LLM, and may be edge-triggered or level-triggered with cooldown.

## Persisted temporal state

The conditional ledger now also records:

- `last_raw_condition_value`
- `true_since_tick`
- `last_condition_value` after sustain qualification
- `last_evaluated_tick`
- `last_fired_tick`

Therefore restart does not erase temporal progress.

## Cost invariant

`nobody_near_entity` intentionally does not enumerate the global manifest. It resolves the anchor, determines its `region_id`, and loads only that region payload.

Future cross-region-radius predicates should use the RegionCatalog/RegionEntityIndex neighborhood rather than global scans.

## Security

Composition and temporal qualification affect only whether an event is proposed. Effects still pass through `GuardedMutationService` and Mutation Gate.

## Non-goals

Still excluded:

- arbitrary executable expressions
- embedded Python/eval
- free-form query languages
- LLM-generated executable predicates
- unbounded global aggregate scans
