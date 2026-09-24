from packages.spatial.region_entity_index import RegionEntityIndex
from packages.spatial.regions import Region, RegionCatalog
from packages.spatial.resolver import SpatialResolver


def make_world(region_count: int, entities_per_region: int = 80):
    regions = []
    entities = []
    spacing = 500.0
    for i in range(region_count):
        rid = f"r{i:03d}"
        neighbors = []
        if i > 0:
            neighbors.append(f"r{i-1:03d}")
        if i + 1 < region_count:
            neighbors.append(f"r{i+1:03d}")
        regions.append(Region(rid, (i * spacing, 0.0), 220.0, "forest", tuple(neighbors)))
        base_x = i * spacing
        for j in range(entities_per_region):
            entities.append({
                "id": f"{rid}-e{j:03d}",
                "region_id": rid,
                "type": "tree",
                "position": {"x": base_x + (j % 10) * 16.0, "y": (j // 10) * 16.0},
            })
    return RegionCatalog(regions), entities


def test_candidate_scan_remains_local_as_universe_grows():
    examined = []
    for region_count in (8, 64, 512):
        catalog, entities = make_world(region_count)
        index = RegionEntityIndex(entities)
        middle = region_count // 2
        current = f"r{middle:03d}"
        result = index.candidates(catalog=catalog, current_region_id=current, include_neighbor_depth=1)
        examined.append(result["candidates_examined"])
        assert len(result["region_ids"]) <= 3
        assert result["candidates_examined"] <= 240
        assert index.size() == region_count * 80

    assert examined == [240, 240, 240]


def test_indexed_candidates_feed_real_resolver_with_same_hot_warm_caps():
    catalog, entities = make_world(128)
    index = RegionEntityIndex(entities)
    resolver = SpatialResolver()
    current = "r064"
    candidates = index.candidates(catalog=catalog, current_region_id=current, include_neighbor_depth=1)
    world_slice = resolver.resolve(
        observer={"position": {"x": 64 * 500.0 + 40.0, "y": 40.0}},
        direction={"x": 1.0, "y": 0.0},
        entities=candidates["entities"],
        regions=[catalog.get(r).as_resolver_dict() for r in candidates["region_ids"] if catalog.get(r)],
    )
    assert len(world_slice["hot"]["entity_ids"]) <= 96
    assert len(world_slice["warm"]["entity_ids"]) <= 192
    assert world_slice["cold_omitted"] is True
    assert candidates["candidates_examined"] <= 240


def test_entity_move_updates_region_membership_without_duplicate():
    catalog, entities = make_world(3, entities_per_region=2)
    index = RegionEntityIndex(entities)
    moved = dict(entities[0])
    moved["region_id"] = "r001"
    moved["position"] = {"x": 520.0, "y": 20.0}
    index.upsert(moved)
    r0 = index.entities_for_regions(["r000"])
    r1 = index.entities_for_regions(["r001"])
    assert moved["id"] not in {e["id"] for e in r0}
    assert [e["id"] for e in r1].count(moved["id"]) == 1
