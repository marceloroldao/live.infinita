# Region Spatial Grid 001

## Goal

Remove the remaining full-region scan from observer localization.

Indexed runtime path:

1. bootstrap/rebuild constructs RegionCatalog, RegionEntityIndex and RegionSpatialGrid;
2. an observer bound to an entity resolves its region in O(1)-style hash lookup;
3. an observer represented only by coordinates resolves `position -> region` through one spatial-grid cell;
4. only current region + bounded neighbors feed RegionEntityIndex;
5. only those local candidates feed SpatialResolver.

## Cost model

Normal indexed delivery no longer constructs global entity/region candidate lists.

The expensive O(N) scan is permitted only during bootstrap/rebuild/fallback recovery. Normal deltas patch indexed entities directly.

Synthetic validation covers 64, 1,024 and 16,384 regions. With 300-unit spacing and 256-unit cells, a point lookup examines at most a small constant number of region candidates rather than all regions.

## Telemetry

`world.interest` and `delivery` expose:

- `region_lookup_mode`
- `region_candidates_examined`
- `candidates_examined`
- `source_regions_total`
- `source_entities_total`

This makes the scaling property observable rather than assumed.
