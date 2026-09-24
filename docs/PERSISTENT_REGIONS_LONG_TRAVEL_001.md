# Persistent Regions + Long Travel 001

## Goal

Validate that Live.infinita can grow the persistent universe without growing the renderer's local materialization cost proportionally.

## Region identity

A region is persistent metadata, not a loaded scene. Minimum fields:

- `id`
- `center`
- `radius`
- `biome`
- `neighbors`
- optional metadata

The current `RegionCatalog` is intentionally small and deterministic. It is an adapter boundary: later Memoria.ia/DBR can back region identity/topology without changing `SpatialResolver`.

## Long-travel test

The automated scenario builds 48 connected regions with 80 persistent entities per region: 3,840 entities total. Nov's observer position crosses the entire chain while heading forward.

At every step the test requires:

- HOT <= 96 entities
- WARM <= 192 entities
- cold state omitted from the local payload
- many different regions become hot over the journey

A second scaling test grows the universe through 8, 24 and 64 regions while asserting that HOT/WARM caps remain unchanged.

## Architecture principle

Universe size and presentation cost are separate variables.

```text
persistent universe
  -> region identity/topology
  -> observer position + direction
  -> SpatialResolver
  -> bounded HOT/WARM slice
  -> renderer
```

The current resolver still receives candidate arrays in memory; this test validates bounded output, not yet bounded lookup cost. The next optimization is region-indexed candidate retrieval so the resolver never scans the entire persistent universe.
