# Spatial Resolver 001 — Live.infinita

## Objective

Keep render/runtime cost bounded by observer relevance rather than total world size.

## Inputs

- observer position
- observer movement direction
- candidate entities
- candidate regions
- semantic salience/importance when available

## Output

```json
{
  "hot": {"entity_ids": [], "region_ids": []},
  "warm": {"entity_ids": [], "region_ids": []},
  "cold_omitted": true
}
```

Cold world state is deliberately omitted from the local slice.

## Policy

Default policy:

- hot radius: 180 logical units
- warm radius: 420 logical units
- hot entity cap: 96
- warm entity cap: 192
- forward direction contributes to warm priority
- semantic importance contributes to priority but does not override the hot distance boundary

The caps are hard limits for materialization payloads; they do not limit how many objects may exist in the persistent universe.

## Separation of concerns

Memoria.ia / DBR may persist the global world, history, identities, relations and unresolved regional state.

Spatial Resolver selects what is relevant now.

World Runtime remains authoritative for factual state.

Godot materializes only the resolved local slice.

## Example: Nov in a forest

If Nov walks north:

- nearby forest objects become hot
- objects and regions ahead are preferentially warm
- distant regions remain cold and are not sent to the renderer
- a semantically important object can outrank an ordinary warm object
- it does not become hot unless it crosses the hot boundary

This keeps geometry/materialization cost approximately proportional to local relevance rather than world extent.
