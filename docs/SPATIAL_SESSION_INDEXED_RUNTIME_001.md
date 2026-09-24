# Spatial Session Indexed Runtime 001

## Goal

Move the Region Entity Index from an isolated proof into the actual observer-local Runtime delivery path.

## Runtime behavior

For worlds where every persistent entity has `region_id` and regions have stable IDs:

1. SpatialSession bootstraps one shared RegionEntityIndex.
2. The observer entity resolves its authoritative position from the index.
3. The observer region is resolved from the entity's indexed `region_id`.
4. Only current region + depth-1 neighbor regions are queried.
5. SpatialResolver receives only those local candidates.
6. WebSocket delivery still emits `type: world_state`, with HOT entities materialized and WARM metadata only.

Legacy worlds without complete region identity continue through `legacy_global_scan`.

## Incremental updates

When a World State message carries a delta, entity operations update only affected index entries. A bootstrap reset triggers a rebuild. If the Runtime cannot safely interpret an update, it falls back to rebuilding rather than returning stale spatial truth.

## Observability

`world.interest` and `delivery` expose:

- `mode`: `region_entity_index` or `legacy_global_scan`
- `current_region_id`
- `candidates_examined`
- `candidate_region_ids`
- `indexed_entities_total`

These fields make it possible to prove that search cost remains local while total persistent world size grows.

## Multi-observer model

The RegionEntityIndex is shared global world truth. Observer view state remains per WebSocket. Multiple observers therefore reuse the same index while receiving independent local slices.

This is intentional: duplicating the full spatial index for every observer would make memory usage scale with observer count.
