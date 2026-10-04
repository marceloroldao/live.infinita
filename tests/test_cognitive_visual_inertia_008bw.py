from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "cognitive_terrain_visual_stability.py"
spec = importlib.util.spec_from_file_location("cognitive_visual_stability_008bw", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def raw_projection(
    pid: str,
    *,
    elevation: float = 0.0,
    radius: float = 115.0,
    mass: float = 0.0,
    role: str = "memory_field",
    lake: bool = False,
    ridge_height: float = 1.0,
    ridge_width: float = 28.0,
    relation_strength: float = 0.0,
    relation_count: int = 0,
    trail_strength: float = 0.0,
    trail_candidate: bool = False,
    include_transition: bool = True,
    include_spatial: bool = False,
) -> dict:
    transitions = []
    if include_transition:
        transitions.append({
            "from_region_id": "a",
            "to_region_id": "b",
            "count": relation_count,
            "strength": relation_strength,
            "ridge_height_m": ridge_height,
            "ridge_width_m": ridge_width,
            "trail_strength": trail_strength,
            "trail_width_m": 0.7 + trail_strength,
            "trail_candidate": trail_candidate,
        })
    spatial = []
    if include_spatial:
        spatial.append({
            "from_position": {"x": 0.0, "y": 0.0},
            "to_position": {"x": 64.0, "y": 0.0},
            "from_region_id": "a",
            "to_region_id": "b",
            "count": relation_count,
            "trail_strength": trail_strength,
            "trail_width_m": 0.6 + trail_strength,
            "trail_candidate": trail_candidate,
        })
    return {
        "schema": "live-infinita-cognitive-terrain/v1",
        "projection_id": pid,
        "world_id": "world-test",
        "policy": {
            "visual_only": True,
            "world_write_authority": False,
            "selection_authority": False,
        },
        "regions": [
            {
                "region_id": "a",
                "center": {"x": 0.0, "y": 0.0},
                "elevation_bias_m": elevation,
                "influence_radius_m": radius,
                "cognitive_mass": mass,
                "terrain_role": role,
                "lake_candidate": lake,
            },
            {
                "region_id": "b",
                "center": {"x": 160.0, "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 115.0,
                "cognitive_mass": 0.0,
                "terrain_role": "memory_field",
                "lake_candidate": False,
            },
        ],
        "transitions": transitions,
        "spatial_trails": spatial,
    }


def region(result: dict, region_id: str = "a") -> dict:
    return next(row for row in result["visual_regions"] if row["region_id"] == region_id)


def transition(result: dict) -> dict:
    return result["visual_transitions"][0]


class CognitiveVisualInertia008BWTests(unittest.TestCase):
    def test_bootstrap_matches_current_map_without_jump(self) -> None:
        raw = raw_projection(
            "ctp_boot",
            elevation=8.0,
            radius=170.0,
            mass=0.8,
            role="uplift",
            ridge_height=9.0,
            ridge_width=80.0,
            relation_strength=0.9,
            relation_count=12,
            trail_strength=0.7,
            trail_candidate=True,
        )
        result = module.stabilize_visual_projection(raw, None)
        self.assertTrue(result["visual_stability"]["bootstrap"])
        self.assertEqual(region(result)["elevation_bias_m"], 8.0)
        self.assertEqual(region(result)["terrain_role"], "uplift")
        self.assertEqual(transition(result)["ridge_height_m"], 9.0)
        self.assertEqual(transition(result)["strength"], 0.9)
        self.assertTrue(transition(result)["trail_candidate"])

    def test_stable_target_does_not_age_without_need(self) -> None:
        raw = raw_projection("ctp_same", elevation=4.0, mass=0.5)
        first = module.stabilize_visual_projection(raw, None)
        second = module.stabilize_visual_projection(raw, first)
        self.assertEqual(
            first["visual_projection_id"],
            second["visual_projection_id"],
        )
        self.assertEqual(first["visual_regions"], second["visual_regions"])
        self.assertEqual(
            first["visual_stability"],
            second["visual_stability"],
        )

    def test_large_structural_change_moves_by_bounded_steps(self) -> None:
        base = module.stabilize_visual_projection(
            raw_projection(
                "ctp_base",
                elevation=0.0,
                radius=115.0,
                mass=0.0,
                ridge_height=1.0,
                ridge_width=28.0,
                relation_strength=0.0,
                relation_count=0,
            ),
            None,
        )
        target = raw_projection(
            "ctp_target",
            elevation=12.0,
            radius=190.0,
            mass=1.0,
            role="uplift",
            ridge_height=12.0,
            ridge_width=90.0,
            relation_strength=1.0,
            relation_count=20,
            trail_strength=1.0,
            trail_candidate=True,
        )
        step1 = module.stabilize_visual_projection(target, base)
        a = region(step1)
        e = transition(step1)
        self.assertAlmostEqual(a["elevation_bias_m"], 0.65)
        self.assertAlmostEqual(a["influence_radius_m"], 118.0)
        self.assertAlmostEqual(a["cognitive_mass"], 0.03)
        self.assertEqual(a["terrain_role"], "memory_field")
        self.assertAlmostEqual(e["ridge_height_m"], 1.65)
        self.assertAlmostEqual(e["ridge_width_m"], 31.0)
        self.assertAlmostEqual(e["strength"], 0.05)
        self.assertEqual(e["count"], 2)
        self.assertAlmostEqual(e["trail_strength"], 0.08)
        self.assertFalse(e["trail_candidate"])

        # Same raw projection must keep converging while visual state is not at target.
        step2 = module.stabilize_visual_projection(target, step1)
        self.assertAlmostEqual(region(step2)["elevation_bias_m"], 1.30)
        self.assertAlmostEqual(transition(step2)["ridge_height_m"], 2.30)
        self.assertAlmostEqual(transition(step2)["strength"], 0.10)
        self.assertEqual(transition(step2)["count"], 4)
        self.assertNotEqual(
            step1["visual_projection_id"],
            step2["visual_projection_id"],
        )

    def test_lake_uses_hysteresis_in_both_directions(self) -> None:
        state = module.stabilize_visual_projection(
            raw_projection("ctp_dry", elevation=0.0, lake=False),
            None,
        )
        wet_target = raw_projection(
            "ctp_wet",
            elevation=-10.0,
            role="basin",
            lake=True,
        )

        for _ in range(9):
            state = module.stabilize_visual_projection(wet_target, state)
            self.assertFalse(region(state)["lake_candidate"])
        state = module.stabilize_visual_projection(wet_target, state)
        self.assertLessEqual(region(state)["elevation_bias_m"], -6.5)
        self.assertTrue(region(state)["lake_candidate"])

        dry_target = raw_projection(
            "ctp_dry_again",
            elevation=0.0,
            role="memory_field",
            lake=False,
        )
        first_dry_step = module.stabilize_visual_projection(dry_target, state)
        self.assertTrue(region(first_dry_step)["lake_candidate"])

        state = first_dry_step
        for _ in range(20):
            state = module.stabilize_visual_projection(dry_target, state)
            if not region(state)["lake_candidate"]:
                break
        self.assertFalse(region(state)["lake_candidate"])
        self.assertGreaterEqual(
            region(state)["elevation_bias_m"],
            module.LAKE_DISAPPEAR_ELEVATION_M,
        )

    def test_removed_region_decays_instead_of_popping(self) -> None:
        strong = module.stabilize_visual_projection(
            raw_projection(
                "ctp_region_strong",
                elevation=8.0,
                radius=170.0,
                mass=0.8,
                role="uplift",
            ),
            None,
        )
        target = raw_projection("ctp_region_removed")
        target["regions"] = [
            row for row in target["regions"]
            if row["region_id"] != "a"
        ]

        step1 = module.stabilize_visual_projection(target, strong)
        faded = region(step1, "a")
        self.assertAlmostEqual(faded["elevation_bias_m"], 7.35)
        self.assertAlmostEqual(faded["influence_radius_m"], 167.0)
        self.assertAlmostEqual(faded["cognitive_mass"], 0.77)
        self.assertEqual(faded["terrain_role"], "uplift")

        state = step1
        for _ in range(40):
            state = module.stabilize_visual_projection(target, state)
            if not any(
                row["region_id"] == "a"
                for row in state["visual_regions"]
            ):
                break
        self.assertFalse(any(
            row["region_id"] == "a"
            for row in state["visual_regions"]
        ))

    def test_raw_projection_stays_immediate_while_visual_projection_is_slow(self) -> None:
        base = module.stabilize_visual_projection(
            raw_projection("ctp_raw_base", elevation=0.0, mass=0.0),
            None,
        )
        target = raw_projection(
            "ctp_raw_target",
            elevation=12.0,
            mass=1.0,
            role="uplift",
        )
        result = module.stabilize_visual_projection(target, base)
        raw_a = next(row for row in result["regions"] if row["region_id"] == "a")
        visual_a = region(result)
        self.assertEqual(raw_a["elevation_bias_m"], 12.0)
        self.assertEqual(raw_a["cognitive_mass"], 1.0)
        self.assertAlmostEqual(visual_a["elevation_bias_m"], 0.65)
        self.assertAlmostEqual(visual_a["cognitive_mass"], 0.03)
        self.assertTrue(
            result["visual_stability"]["policy"]["raw_projection_remains_authoritative"]
        )

    def test_removed_ridge_and_trail_decay_instead_of_popping(self) -> None:
        strong = module.stabilize_visual_projection(
            raw_projection(
                "ctp_strong",
                ridge_height=9.0,
                ridge_width=80.0,
                relation_strength=0.9,
                relation_count=12,
                trail_strength=0.8,
                trail_candidate=True,
            ),
            None,
        )
        empty = raw_projection(
            "ctp_empty",
            include_transition=False,
        )
        step1 = module.stabilize_visual_projection(empty, strong)
        self.assertEqual(len(step1["visual_transitions"]), 1)
        self.assertAlmostEqual(
            transition(step1)["ridge_height_m"],
            8.35,
        )
        self.assertAlmostEqual(
            transition(step1)["trail_strength"],
            0.72,
        )
        self.assertTrue(transition(step1)["trail_candidate"])

        state = step1
        for _ in range(30):
            state = module.stabilize_visual_projection(empty, state)
            if not state["visual_transitions"]:
                break
        self.assertEqual(state["visual_transitions"], [])

    def test_refresh_hint_matches_two_minute_projection_timer(self) -> None:
        timer = (
            ROOT / "deploy" / "live-infinita-cognitive-terrain.timer"
        ).read_text(encoding="utf-8")
        self.assertEqual(module.VISUAL_REFRESH_HINT_SECONDS, 120)
        self.assertIn("OnUnitInactiveSec=2min", timer)

    def test_raw_plus_visual_worst_case_fits_projection_file_budget(self) -> None:
        raw = raw_projection("ctp_size_budget")
        raw["regions"] = [
            {
                "region_id": f"region_{i:02d}",
                "center": {"x": float(i * 64), "y": float((i % 8) * 64)},
                "elevation_bias_m": 12.0 if i % 2 else -10.0,
                "influence_radius_m": 220.0,
                "cognitive_mass": 1.0,
                "terrain_role": "uplift" if i % 2 else "basin",
                "lake_candidate": not bool(i % 2),
            }
            for i in range(32)
        ]
        raw["transitions"] = [
            {
                "from_region_id": f"region_{i % 32:02d}",
                "to_region_id": f"region_{(i + 1) % 32:02d}",
                "count": 100000,
                "strength": 1.0,
                "ridge_height_m": 14.0,
                "ridge_width_m": 96.0,
                "trail_strength": 1.0,
                "trail_width_m": 3.0,
                "trail_candidate": True,
            }
            for i in range(48)
        ]
        raw["spatial_trails"] = [
            {
                "from_position": {"x": float(i * 4), "y": float(i * 3)},
                "to_position": {"x": float(i * 4 + 64), "y": float(i * 3 + 64)},
                "from_region_id": f"region_{i % 32:02d}",
                "to_region_id": f"region_{(i + 1) % 32:02d}",
                "count": 100000,
                "trail_strength": 1.0,
                "trail_width_m": 3.0,
                "trail_candidate": True,
            }
            for i in range(128)
        ]
        result = module.stabilize_visual_projection(raw, None)
        encoded = module._canonical(result)
        self.assertLess(len(encoded), 128 * 1024)

    def test_visual_fields_remain_within_renderer_budgets(self) -> None:
        raw = raw_projection("ctp_budget")
        raw["regions"] = [
            {
                "region_id": f"r{i:02d}",
                "center": {"x": float(i), "y": 0.0},
                "elevation_bias_m": 0.0,
                "influence_radius_m": 115.0,
                "cognitive_mass": 0.0,
                "terrain_role": "memory_field",
                "lake_candidate": False,
            }
            for i in range(40)
        ]
        raw["transitions"] = [
            {
                "from_region_id": f"r{i % 32:02d}",
                "to_region_id": f"r{(i + 1) % 32:02d}",
                "count": i,
                "strength": 1.0,
                "ridge_height_m": 9.0,
                "ridge_width_m": 80.0,
                "trail_strength": 0.5,
                "trail_width_m": 1.2,
                "trail_candidate": True,
            }
            for i in range(70)
        ]
        raw["spatial_trails"] = [
            {
                "from_position": {"x": float(i), "y": 0.0},
                "to_position": {"x": float(i + 1), "y": 0.0},
                "count": 3,
                "trail_strength": 0.6,
                "trail_width_m": 1.0,
                "trail_candidate": True,
            }
            for i in range(160)
        ]
        result = module.stabilize_visual_projection(raw, None)
        self.assertLessEqual(len(result["visual_regions"]), 32)
        self.assertLessEqual(len(result["visual_transitions"]), 48)
        self.assertLessEqual(len(result["visual_spatial_trails"]), 128)


if __name__ == "__main__":
    unittest.main()
