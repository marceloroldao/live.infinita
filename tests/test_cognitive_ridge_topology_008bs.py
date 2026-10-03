from pathlib import Path
import importlib.util
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
spec = importlib.util.spec_from_file_location("cognitive_ridge_topology_008bs", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

REGIONS = [
    {"region_id": "a", "center": {"x": 0.0, "y": 0.0}, "biome": "hills"},
    {"region_id": "b", "center": {"x": 160.0, "y": 0.0}, "biome": "forest"},
    {"region_id": "c", "center": {"x": 320.0, "y": 0.0}, "biome": "meadow"},
]


def projection(records):
    return module.build_projection(
        world_id="w",
        known_regions=REGIONS,
        records=records,
        source_snapshot_records=len(records),
        checkpoint_cursor=len(records),
    )


class CognitiveRidgeTopology008BSTests(unittest.TestCase):
    def test_recurrent_high_mass_edge_gets_more_relief_than_weak_edge(self) -> None:
        records = []
        tick = 0
        for _ in range(12):
            tick += 10
            records.append({"logical_tick": tick, "region_id": "a", "need": "explore"})
            tick += 10
            records.append({"logical_tick": tick, "region_id": "b", "need": "explore"})
        tick += 10
        records.append({"logical_tick": tick, "region_id": "c", "need": "explore"})

        p = projection(records)
        edges = {(r["from_region_id"], r["to_region_id"]): r for r in p["transitions"]}
        strong = edges[("a", "b")]
        weak = edges[("b", "c")]

        self.assertGreater(strong["ridge_height_m"], weak["ridge_height_m"])
        self.assertGreater(strong["ridge_width_m"], weak["ridge_width_m"])
        self.assertGreater(strong["ridge_height_m"], 4.5)
        self.assertLessEqual(strong["ridge_height_m"], 14.0)
        self.assertLessEqual(strong["ridge_width_m"], 96.0)

    def test_ridge_formula_uses_only_existing_aggregate_endpoint_state(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8")
        self.assertIn("endpoint_mass = sqrt(", source)
        self.assertIn("elevation_support = 0.5 * (", source)
        self.assertIn("masses[source]", source)
        self.assertIn("masses[target]", source)
        self.assertIn("elevation_by_region.get(source", source)
        self.assertIn("elevation_by_region.get(target", source)
        self.assertIn("14.0", source)
        self.assertNotIn("random.", source)
        self.assertNotIn("GuardedMutationService", source)

    def test_zero_memory_does_not_create_transition_ridges(self) -> None:
        p = projection([])
        self.assertEqual(p["transitions"], [])

    def test_renderer_accepts_bounded_fourteen_meter_ridges(self) -> None:
        source = (
            ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"height": clampf(float(row.get("ridge_height_m", 1.0)), 0.0, 14.0)',
            source,
        )
        self.assertIn("return clampf(total, MAX_BASIN_M, MAX_UPLIFT_M)", source)


if __name__ == "__main__":
    unittest.main()
