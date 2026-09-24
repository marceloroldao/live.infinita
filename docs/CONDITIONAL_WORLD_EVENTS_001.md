# Conditional World Events 001

## Goal

Allow the logical world to react deterministically to authoritative state, without requiring an LLM or renderer loop to poll and improvise behavior.

## Tick ordering

For logical tick N:

1. SimulationClock advances to N.
2. Time-scheduled world events due at N fire.
3. Conditional events evaluate authoritative state after those time events.
4. Active character plans execute at most one step each.
5. Renderer receives the resulting authoritative/spatial state independently of FPS.

This ordering is deliberate. A scheduled event such as `period=night` can trigger a conditional event such as `turn village lamps on` in the same logical tick, before character plans execute.

## Supported predicates v1

- `entity_in_region`
- `world_equals`
- `entity_property_equals`

Predicates are deterministic reads only. They never mutate world state.

## Trigger modes

### edge

Default. Fires only on a false -> true transition. A continuously true condition does not repeatedly generate events.

Example:

`Nov enters village -> ring bell`

It fires once on entry, not on every tick while Nov remains inside.

### level

May fire while a condition remains true, subject to `cooldown_ticks`.

Example:

`while night, refresh a periodic world behavior every 120 ticks`

## one_shot

A successful one-shot condition becomes `completed` after its first authoritative mutation.

Example:

`when story flag X becomes true -> create unique event Y`

## Cooldown

`cooldown_ticks` is measured only in logical ticks. Wall clock time and renderer FPS do not affect it.

## Authorization

Conditional events do not bypass policy. Their operations are submitted to `GuardedMutationService` and therefore still require a principal accepted by `MutationGate`.

A rejected conditional event becomes `failed` and creates no world mutation.

## Persistence and provenance

The append-only conditional-event ledger records:

- condition definition
- trigger mode
- cooldown
- last condition value
- last evaluated tick
- last fired tick
- fire count
- mutation decision ID
- world event ID
- resulting state hash

This allows replay/audit of why a world change happened.

## Examples

### Nov enters village

Condition:

```json
{"kind":"entity_in_region","entity_id":"nov","region_id":"village"}
```

Effect could be a canonical mutation such as setting a bell or story flag.

### Night turns village lamps on

Condition:

```json
{"kind":"world_equals","path":["environment","period"],"value":"night"}
```

Effect:

```json
{"op":"set","entity_id":"lamp_01","path":["properties","lit"],"value":true}
```

### Entity property trigger

Condition:

```json
{"kind":"entity_property_equals","entity_id":"fire_01","path":["properties","lit"],"value":false}
```

This can drive another deterministic world reaction without involving an LLM.

## Non-goals v1

Not yet included:

- arbitrary Python expressions
- free-form query languages
- distance predicates
- N-tick sustained predicates
- aggregate predicates such as `nobody_near`
- automatic LLM-authored conditions

Those should be added as typed predicates rather than arbitrary executable expressions.
