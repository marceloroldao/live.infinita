from __future__ import annotations
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/world-runtime")]
from npc_environmental_exploration import EnvironmentalExploration, choose_local_region, travel_discomfort
from npc_idle_wander import NpcIdleWander
from packages.spatial.regions import Region, RegionCatalog


class EnvironmentalExplorationTests(unittest.TestCase):
    def setUp(self):
        self.safe = {"current_temperature_c": 20, "slope_deg": 0, "snow_cover": 0,
                     "wetland_affinity": 0, "vegetation_density": 0.3}
        self.cold = {**self.safe, "current_temperature_c": -12, "snow_cover": 1, "slope_deg": 30}
        self.stimulus = {"state_id": "env-test", "regions": {"a": self.safe, "b": self.cold}}

    def test_cold_snow_and_slope_raise_cost(self):
        self.assertGreater(travel_discomfort(self.cold), travel_discomfort(self.safe) + .12)

    def test_wetland_and_dense_vegetation_raise_traversal_cost(self):
        self.assertGreater(travel_discomfort({**self.safe, "wetland_affinity": 1, "vegetation_density": 1}),
                           travel_discomfort(self.safe))

    def test_warm_comfortable_neighbor_is_preferred(self):
        target, reason = choose_local_region(["a", "b"], "b", self.stimulus, 7)
        self.assertEqual(target, "a")
        self.assertEqual(reason["mode"], "environment_preference")

    def test_periodic_exploration_keeps_uncomfortable_neighbor(self):
        target, reason = choose_local_region(["a", "b"], "b", self.stimulus, 19)
        self.assertEqual(target, "b")
        self.assertEqual(reason["mode"], "exploration")

    def test_exploration_slots_eventually_cover_all_candidates(self):
        for count in (2, 3, 4, 5):
            choices = [str(i) for i in range(count)]
            stimulus = {"regions": {key: self.cold if key != "0" else self.safe for key in choices}}
            visited = set()
            for crossing in range(count * 4):
                bucket = crossing * 4 + 3
                visited.add(choose_local_region(choices, choices[crossing % count], stimulus, bucket)[0])
            self.assertEqual(visited, set(choices))

    def test_missing_neighbor_evidence_keeps_original_choice(self):
        target, reason = choose_local_region(["a", "unknown"], "unknown", self.stimulus, 7)
        self.assertEqual(target, "unknown")
        self.assertEqual(reason["mode"], "topology_fallback")

    def test_small_difference_keeps_original_choice(self):
        stimulus = {"regions": {"a": self.safe, "b": {**self.safe, "vegetation_density": .6}}}
        self.assertEqual(choose_local_region(["a", "b"], "b", stimulus, 7)[0], "b")

    def test_deterministic_and_read_only(self):
        before = deepcopy(self.stimulus)
        first = choose_local_region(["a", "b"], "b", self.stimulus, 7)
        self.assertEqual(first, choose_local_region(["a", "b"], "b", self.stimulus, 7))
        self.assertEqual(self.stimulus, before)

    def test_nonfinite_and_malformed_numbers_are_bounded(self):
        cost = travel_discomfort({"slope_deg": float("nan"), "snow_cover": 3,
                                  "wetland_affinity": -1, "current_temperature_c": "bad"})
        self.assertTrue(0 <= cost <= 1)

    def test_missing_projection_is_harmless(self):
        provider = EnvironmentalExploration(lambda: {"world_id": "w"}, ROOT / "missing-test-projection.json")
        self.assertEqual(provider(), {})

    def test_wrong_world_projection_is_rejected(self):
        from cognitive_terrain_projection import CognitiveTerrainError
        provider = EnvironmentalExploration(lambda: {"world_id": "w"}, ROOT / "missing-test-projection.json")
        provider.reader.read = Mock(side_effect=CognitiveTerrainError("projection_contract"))
        self.assertEqual(provider(), {})

    def test_stabilized_projection_used_instead_of_raw(self):
        provider = EnvironmentalExploration(lambda: {"world_id": "w", "regions": [{"id": "a"}]},
                                            ROOT / "missing-test-projection.json")
        provider.reader.read = Mock(return_value={
            "world_id": "w", "projection_id": "raw", "regions": [{"region_id": "a", "elevation_bias_m": 18}],
            "visual_projection_id": "stable", "visual_regions": [{"region_id": "a", "elevation_bias_m": 0}]
        })
        value = provider()
        self.assertLess(value["regions"]["a"]["effective_altitude_m"], 500)

    def test_only_topological_neighbors_can_be_selected(self):
        catalog = RegionCatalog([
            Region("current", (0, 0), 10, neighbors=("a", "b")),
            Region("a", (10, 0), 10), Region("b", (0, 10), 10),
            Region("remote", (100, 100), 10)])
        wander = NpcIdleWander(SimpleNamespace(planner=SimpleNamespace(regions=catalog)), npc_ids=["nov"])
        wander._environmental_stimulus = {**self.stimulus, "regions": {**self.stimulus["regions"], "remote": self.safe}}
        region = wander._select_region({"region_id": "current"}, 7)
        self.assertEqual(region.id, "a")
        self.assertEqual(wander._environmental_decision["candidate_region_ids"], ["a", "b"])

    def test_active_need_does_not_consult_environment_or_schedule(self):
        provider = Mock(return_value=self.stimulus)
        scheduler = SimpleNamespace(planner=SimpleNamespace(store=SimpleNamespace(
            get_entity=lambda _: {"id": "nov", "region_id": "a"})))
        wander = NpcIdleWander(scheduler, npc_ids=["nov"], environmental_provider=provider)
        self.assertEqual(wander.evaluate_tick(4, blocked_npc_ids={"nov"})[0]["status"], "need_active")
        provider.assert_not_called()


if __name__ == "__main__":
    unittest.main()
