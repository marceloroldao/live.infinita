from packages.spatial.regions import Region, RegionCatalog
from packages.spatial.resolver import SpatialResolver


def build_world(region_count: int = 48, entities_per_region: int = 80):
    regions = []
    entities = []
    spacing = 520.0
    radius = 220.0

    for index in range(region_count):
        region_id = f"region-{index:03d}"
        neighbors = []
        if index > 0:
            neighbors.append(f"region-{index - 1:03d}")
        if index + 1 < region_count:
            neighbors.append(f"region-{index + 1:03d}")
        regions.append(
            Region(
                id=region_id,
                center=(index * spacing, 0.0),
                radius=radius,
                biome=("forest", "field", "river", "village")[index % 4],
                neighbors=tuple(neighbors),
            )
        )
        for entity_index in range(entities_per_region):
            x = index * spacing + ((entity_index % 10) - 4.5) * 28.0
            y = ((entity_index // 10) - 3.5) * 34.0
            entities.append(
                {
                    "id": f"{region_id}-entity-{entity_index:03d}",
                    "type": "tree" if entity_index % 3 else "human",
                    "region_id": region_id,
                    "position": {"x": x, "y": y},
                    "properties": {"importance": 1.0 if entity_index == 0 else 0.0},
                }
            )

    return RegionCatalog(regions), entities


def test_region_catalog_finds_long_route():
    catalog, _ = build_world(region_count=32, entities_per_region=1)
    route = catalog.route("region-000", "region-031")
    assert len(route) == 32
    assert route[0] == "region-000"
    assert route[-1] == "region-031"


def test_long_travel_keeps_hot_and_warm_bounded():
    catalog, entities = build_world(region_count=48, entities_per_region=80)
    resolver = SpatialResolver()

    max_hot = 0
    max_warm = 0
    visited_region_ids = set()

    for step in range(48 * 4):
        x = step * (520.0 / 4.0)
        result = resolver.resolve(
            observer={"position": {"x": x, "y": 0.0}},
            entities=entities,
            regions=catalog.resolver_rows(),
            direction={"x": 1.0, "y": 0.0},
        )
        hot = len(result["hot"]["entity_ids"])
        warm = len(result["warm"]["entity_ids"])
        max_hot = max(max_hot, hot)
        max_warm = max(max_warm, warm)
        visited_region_ids.update(result["hot"]["region_ids"])

        assert hot <= result["policy"]["max_hot_entities"]
        assert warm <= result["policy"]["max_warm_entities"]
        assert result["cold_omitted"] is True

    assert len(entities) == 3840
    assert len(catalog.all()) == 48
    assert max_hot <= 96
    assert max_warm <= 192
    assert len(visited_region_ids) > 30


def test_world_growth_does_not_change_slice_caps():
    resolver = SpatialResolver()
    snapshots = []
    for region_count in (8, 24, 64):
        catalog, entities = build_world(region_count=region_count, entities_per_region=120)
        midpoint = (region_count // 2) * 520.0
        result = resolver.resolve(
            observer={"position": {"x": midpoint, "y": 0.0}},
            entities=entities,
            regions=catalog.resolver_rows(),
            direction={"x": 1.0, "y": 0.0},
        )
        snapshots.append((len(entities), len(result["hot"]["entity_ids"]), len(result["warm"]["entity_ids"])))

    assert snapshots[0][0] < snapshots[1][0] < snapshots[2][0]
    for _, hot, warm in snapshots:
        assert hot <= 96
        assert warm <= 192
