from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from environmental_rules import derive_environmental_state, region_environment_map


def world() -> dict:
    return {
        "world_id": "env-test",
        "environment": {
            "period": "day",
            "weather": "clear",
            "atmosphere_intensity": 0.58,
            "climate": {
                "base_altitude_m": 180.0,
                "base_temperature_c": 22.0,
                "annual_precipitation_mm": 1400.0,
            },
        },
        "regions": [
            {"id": "peak", "biome": "highlands", "radius": 170.0},
            {"id": "forest", "biome": "forest", "radius": 150.0},
            {"id": "basin", "biome": "meadow", "radius": 140.0},
        ],
    }


def projection(*, peak_bias: float = 18.0) -> dict:
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": f"ctp-{peak_bias}",
        "world_id": "env-test",
        "regions": [
            {
                "region_id": "peak",
                "biome": "highlands",
                "cognitive_mass": 1.0,
                "terrain_role": "uplift",
                "elevation_bias_m": peak_bias,
                "influence_radius_m": 180.0,
                "lake_candidate": False,
            },
            {
                "region_id": "forest",
                "biome": "forest",
                "cognitive_mass": 0.62,
                "terrain_role": "memory_field",
                "elevation_bias_m": 2.0,
                "influence_radius_m": 150.0,
                "lake_candidate": False,
            },
            {
                "region_id": "basin",
                "biome": "meadow",
                "cognitive_mass": 0.1,
                "terrain_role": "basin",
                "elevation_bias_m": -10.0,
                "influence_radius_m": 140.0,
                "lake_candidate": True,
            },
        ],
    }


class EnvironmentalRules008BETests(unittest.TestCase):
    def test_high_cognitive_uplift_becomes_cold_rocky_and_blocks_trees(self) -> None:
        state = derive_environmental_state(world(), projection())
        regions = region_environment_map(state)
        peak = regions["peak"]
        self.assertGreater(peak["effective_altitude_m"], 3000.0)
        self.assertLess(peak["climate_temperature_c"], 2.0)
        self.assertGreater(peak["snow_cover"], 0.2)
        self.assertGreater(peak["rock_exposure"], 0.6)
        self.assertFalse(peak["trees_allowed"])
        self.assertIn(peak["ecological_zone"], {"alpine_rock", "snowfield"})

    def test_basin_is_wetter_than_mid_elevation_forest(self) -> None:
        state = derive_environmental_state(world(), projection())
        regions = region_environment_map(state)
        self.assertGreater(
            regions["basin"]["soil_moisture"],
            regions["forest"]["soil_moisture"],
        )
        self.assertGreater(regions["basin"]["water_influence"], 0.9)

    def test_environment_changes_when_cognitive_elevation_changes(self) -> None:
        high = region_environment_map(
            derive_environmental_state(world(), projection(peak_bias=18.0))
        )["peak"]
        low = region_environment_map(
            derive_environmental_state(world(), projection(peak_bias=2.0))
        )["peak"]
        self.assertGreater(high["effective_altitude_m"], low["effective_altitude_m"])
        self.assertLess(high["climate_temperature_c"], low["climate_temperature_c"])
        self.assertGreater(high["rock_exposure"], low["rock_exposure"])

    def test_projection_is_read_only_deterministic_and_bounded(self) -> None:
        source_world = world()
        source_projection = projection()
        before_world = deepcopy(source_world)
        before_projection = deepcopy(source_projection)
        first = derive_environmental_state(source_world, source_projection)
        second = derive_environmental_state(source_world, source_projection)
        self.assertEqual(first, second)
        self.assertEqual(source_world, before_world)
        self.assertEqual(source_projection, before_projection)
        self.assertFalse(first["policy"]["world_write_authority"])
        self.assertFalse(first["policy"]["memory_is_authority"])
        self.assertEqual(first["schema"], "live-infinita-environmental-state/v1")
        for row in first["regions"]:
            for key in (
                "soil_moisture",
                "snow_cover",
                "rock_exposure",
                "vegetation_density",
                "tree_suitability",
            ):
                self.assertGreaterEqual(row[key], 0.0)
                self.assertLessEqual(row[key], 1.0)


if __name__ == "__main__":
    unittest.main()
