# Region Transition 001 — Live.infinita

## Goal

Allow an observer such as Nov to cross very large worlds without loading or rendering the full map. The renderer only receives the active local slice plus the semantic identity of the next region and blends presentation across the boundary.

## World-state contract

```json
{
  "environment": {
    "period": "day",
    "biome": "forest",
    "weather": "clear",
    "atmosphere_intensity": 0.55,
    "transition": {
      "to_region_id": "field_north_002",
      "to_biome": "field",
      "progress": 0.35,
      "direction": "north"
    }
  }
}
```

Only `to_biome` and `progress` are required by the current renderer. Region identifiers and direction are preserved for the future spatial resolver.

## Semantics

- `biome` is the current resolved region type.
- `transition.to_biome` is the adjacent region being entered.
- `transition.progress` is clamped to 0..1.
- progress 0 means 100% current biome.
- progress 1 means 100% next biome.
- absence of `transition` means no blend.

## Presentation

Atmospheric effects are blended by weight rather than abruptly replaced:

- forest: mist and motes
- field: light wind traces
- river: local shimmer/water tint
- village: sparse warm distant glow

Weather remains orthogonal. Rain can therefore occur over forest, field, river or village without changing the persisted region identity.

## Scaling model

The global world is not sent to the renderer. A future Spatial Resolver should supply:

1. hot slice — currently perceivable/interactable entities;
2. warm boundary — semantic metadata for the likely next region;
3. cold world — remains in Memoria.ia/DBR and is not materialized graphically.

Transition metadata is therefore a prefetch hint and presentation hint, not a second loaded map.

## Invariant

World identity and entity history remain authoritative outside the renderer. The renderer may interpolate appearance but must never manufacture persistent facts from visual effects.
