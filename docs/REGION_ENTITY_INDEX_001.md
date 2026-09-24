# Region Entity Index 001

## Goal

Keep spatial search cost local as the persistent universe grows.

## Model

`RegionCatalog` owns region identity/topology.

`RegionEntityIndex` maps persistent entity identity to a region bucket. It is a candidate-selection layer only; it does not become the source of truth for entities.

For an observer in region `R`, candidate selection uses:

- current region `R`
- direct neighbors of `R` (depth 1 by default)

Only entities from those buckets are passed to `SpatialResolver`.

## Complexity target

Before the index, resolver candidate work was proportional to total world entities because callers supplied the global entity list.

With the index, candidate work is proportional to the bounded local neighborhood:

`candidate_cost ≈ entities_per_region × local_region_count`

not:

`candidate_cost ≈ total_world_entities`

The default test topology uses one current region plus up to two neighbors. At 80 entities/region the resolver examines at most 240 candidates whether the universe has 8, 64, or 512 regions.

## Invariants

- entity ids remain globally stable
- moving an entity updates its region bucket without duplication
- cold entities never enter resolver input
- HOT remains capped at 96
- WARM remains capped at 192
- index can later be backed by Memoria.ia/DBR region queries

## Next integration

Replace global entity-list input in spatial session/runtime with candidate retrieval from a persistent Region Entity Index or Memoria.ia/DBR query adapter.
