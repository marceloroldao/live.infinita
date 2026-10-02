from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cold_engine import ColdAuthoritativeWorldEngine
from cognitive_world_builder import CognitiveWorldBuilderAgent, AGENT_ID
from mutation_gate_service import GuardedMutationService
from packages.spatial import FileRegionColdStore
from simulation_clock import SimulationClock
from world_tick import WorldTickRunner


class CognitiveWorldBuilder008CTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bootstrap = self.root / "bootstrap.json"
        self.data = self.root / "autonomous-world"
        self.cold = self.root / "cold-store"
        self.projection = self.root / "cognitive-terrain" / "projection.json"
        self.projection.parent.mkdir(parents=True)
        self.bootstrap.write_text(json.dumps({
            "world_id": "builder-test",
            "version": 1,
            "sequence": 0,
            "regions": [
                {
                    "id": "shelter",
                    "center": {"x": 100.0, "y": 100.0},
                    "radius": 120.0,
                    "biome": "forest",
                    "neighbors": ["clearing"],
                },
                {
                    "id": "clearing",
                    "center": {"x": 360.0, "y": 100.0},
                    "radius": 150.0,
                    "biome": "clearing",
                    "neighbors": ["shelter", "meadow"],
                },
                {
                    "id": "meadow",
                    "center": {"x": 650.0, "y": 160.0},
                    "radius": 130.0,
                    "biome": "meadow",
                    "neighbors": ["clearing"],
                },
            ],
            "environment": {"period": "day", "biome": "forest"},
            "entities": [
                {
                    "id": "nov",
                    "type": "human",
                    "region_id": "clearing",
                    "position": {"x": 360.0, "y": 100.0},
                    "properties": {"observer": True},
                },
            ],
            "narration": {"text": ""},
        }), encoding="utf-8")
        self.store = FileRegionColdStore(self.cold)
        self.engine = ColdAuthoritativeWorldEngine(self.bootstrap, self.data, self.store)
        self.guarded = GuardedMutationService(
            self.engine, decision_log_file=self.data / "mutation-decisions.jsonl"
        )
        self._write_projection()
        self.builder = CognitiveWorldBuilderAgent(
            self.store,
            self.guarded,
            self.engine.load_world,
            projection_file=self.projection,
            interval_ticks=240,
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_projection(
        self,
        *,
        world_write_authority: bool = False,
        malicious_center: bool = False,
        shelter_bias: float = 18.0,
    ) -> None:
        shelter_center = {"x": 999999.0, "y": -999999.0} if malicious_center else {"x": 100.0, "y": 100.0}
        self.projection.write_text(json.dumps({
            "schema": "live-infinita-cognitive-terrain/v1",
            "projection_id": "ctp_builder_fixture",
            "world_id": "builder-test",
            "source": {
                "kind": "memoria.ia-v2-confirmed-nov-episodes",
                "snapshot_records": 120,
                "nov_observations": 120,
                "checkpoint_cursor": 120,
                "latest_logical_tick": 1000,
            },
            "policy": {
                "visual_only": True,
                "world_write_authority": world_write_authority,
                "selection_authority": False,
                "max_regions": 32,
                "max_transitions": 48,
                "episode_window_limit": 8192,
                "height_cap_m": 18.0,
                "basin_cap_m": -12.0,
            },
            "regions": [
                {
                    "region_id": "shelter",
                    "center": shelter_center,
                    "biome": "forest",
                    "visits": 90,
                    "cognitive_mass": 0.99,
                    "terrain_role": "uplift",
                    "elevation_bias_m": shelter_bias,
                    "influence_radius_m": 180.0,
                    "lake_candidate": False,
                },
                {
                    "region_id": "clearing",
                    "center": {"x": 360.0, "y": 100.0},
                    "biome": "clearing",
                    "visits": 25,
                    "cognitive_mass": 0.82,
                    "terrain_role": "memory_field",
                    "elevation_bias_m": 8.0,
                    "influence_radius_m": 150.0,
                    "lake_candidate": False,
                },
                {
                    "region_id": "meadow",
                    "center": {"x": 650.0, "y": 160.0},
                    "biome": "meadow",
                    "visits": 0,
                    "cognitive_mass": 0.0,
                    "terrain_role": "basin",
                    "elevation_bias_m": -10.0,
                    "influence_radius_m": 120.0,
                    "lake_candidate": True,
                },
            ],
            "transitions": [],
        }), encoding="utf-8")

    def test_off_interval_does_nothing(self) -> None:
        self.assertEqual(self.builder.evaluate_tick(239), [])
        self.assertEqual(self.store.entities_total(), 1)

    def test_high_uplift_creates_rock_via_environment_and_world_agent_gate(self) -> None:
        result = self.builder.evaluate_tick(240)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "created")
        self.assertEqual(result[0]["environmental_basis"], "rock_exposure")
        self.assertEqual(result[0]["environmental_zone"], "alpine_rock")
        entity_id = result[0]["entity_id"]
        entity = self.store.get_entity(entity_id)
        self.assertIsNotNone(entity)
        self.assertEqual(entity["type"], "rock")
        self.assertEqual(entity["region_id"], "shelter")
        origin = entity["properties"]["builder_origin"]
        self.assertEqual(origin["agent_id"], AGENT_ID)
        self.assertEqual(origin["environmental_basis"], "rock_exposure")
        self.assertGreater(origin["environmental_score"], 0.6)
        self.assertFalse(origin["memory_is_authority"])
        self.assertTrue(origin["world_write_via_mutation_gate"])
        self.assertTrue(self.engine.verify_replay()["ok"])

        events = self.engine.read_jsonl(self.engine.events_file)
        self.assertEqual(events[-1]["source"], "cognitive_world_builder")
        deltas = self.engine.read_jsonl(self.engine.deltas_file)
        self.assertEqual(deltas[-1]["operations"][0]["op"], "create")

    def test_moderate_uplift_can_still_create_tree_when_environment_allows(self) -> None:
        self._write_projection(shelter_bias=2.0)
        builder = CognitiveWorldBuilderAgent(
            self.store,
            self.guarded,
            self.engine.load_world,
            projection_file=self.projection,
            interval_ticks=240,
        )
        result = builder.evaluate_tick(240)[0]
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["entity_type"], "tree")
        self.assertEqual(result["environmental_basis"], "tree_suitability")
        entity = self.store.get_entity(result["entity_id"])
        self.assertEqual(entity["type"], "tree")


    def test_repeated_ticks_fill_environmental_slots_without_duplicates(self) -> None:
        first = self.builder.evaluate_tick(240)[0]
        second = self.builder.evaluate_tick(480)[0]
        third = self.builder.evaluate_tick(720)[0]
        stable = self.builder.evaluate_tick(960)[0]
        self.assertEqual(first["status"], "created")
        self.assertEqual(second["status"], "created")
        self.assertEqual(third["status"], "created")
        self.assertEqual(first["entity_type"], "rock")
        self.assertEqual(second["entity_type"], "rock")
        self.assertEqual(third["entity_type"], "rest_point")
        ids = {first["entity_id"], second["entity_id"], third["entity_id"]}
        self.assertEqual(len(ids), 3)
        self.assertEqual(self.store.entities_total(), 4)
        self.assertEqual(stable["status"], "stable")
        self.assertEqual(self.store.entities_total(), 4)
        self.assertTrue(self.engine.verify_replay()["ok"])


    def test_projection_coordinates_never_choose_canonical_position(self) -> None:
        self._write_projection(malicious_center=True)
        builder = CognitiveWorldBuilderAgent(
            self.store,
            self.guarded,
            self.engine.load_world,
            projection_file=self.projection,
            interval_ticks=240,
        )
        result = builder.evaluate_tick(240)[0]
        entity = self.store.get_entity(result["entity_id"])
        self.assertIsNotNone(entity)
        p = entity["position"]
        distance = math.hypot(p["x"] - 100.0, p["y"] - 100.0)
        self.assertLess(distance, 120.0)
        self.assertLess(abs(p["x"]), 1000.0)
        self.assertLess(abs(p["y"]), 1000.0)

    def test_invalid_projection_authority_is_rejected_without_mutation(self) -> None:
        self._write_projection(world_write_authority=True)
        before_hash = self.engine.load_world()["state_hash"]
        result = self.builder.evaluate_tick(240)
        self.assertEqual(result[0]["status"], "projection_rejected")
        self.assertEqual(self.store.entities_total(), 1)
        self.assertEqual(self.engine.load_world()["state_hash"], before_hash)

    def test_basin_produces_rest_point_after_higher_priority_rock_growth(self) -> None:
        self.builder.evaluate_tick(240)
        self.builder.evaluate_tick(480)
        row = self.builder.evaluate_tick(720)[0]
        self.assertEqual(row["role"], "basin")
        self.assertEqual(row["entity_type"], "rest_point")
        self.assertEqual(row["environmental_basis"], "water_influence")
        entity = self.store.get_entity(row["entity_id"])
        self.assertEqual(entity["region_id"], "meadow")
        self.assertEqual(entity["properties"]["label"], "Marco de descanso")


    def test_source_contract_keeps_builder_disabled_by_default(self) -> None:
        source = (RUNTIME / "autonomous_runtime.py").read_text(encoding="utf-8")
        main = (RUNTIME / "autonomous_runtime_main.py").read_text(encoding="utf-8")
        tick = (RUNTIME / "world_tick.py").read_text(encoding="utf-8")
        builder = (RUNTIME / "cognitive_world_builder.py").read_text(encoding="utf-8")
        self.assertIn("world_builder_enabled: bool = False", source)
        self.assertIn('_flag_enabled("LIVE_INFINITA_WORLD_BUILDER")', main)
        self.assertIn('"world_builder.evaluate"', tick)
        self.assertIn('"world_builder": world_builder_results', tick)
        self.assertIn("MAX_BUILDER_ENTITIES = 48", builder)
        self.assertIn("MAX_CREATIONS_PER_TICK = 1", builder)

    def test_rollout_enables_builder_only_in_autonomous_single_writer(self) -> None:
        dropin = (ROOT / "deploy" / "live-infinita-autonomous-world-builder.conf").read_text(encoding="utf-8")
        script = (ROOT / "deploy" / "apply-cognitive-builder-008c.sh").read_text(encoding="utf-8")
        self.assertIn('LIVE_INFINITA_WORLD_BUILDER=1', dropin)
        self.assertIn('LIVE_INFINITA_WORLD_BUILDER_INTERVAL_TICKS=240', dropin)
        self.assertIn('/var/lib/live-infinita/cognitive-terrain/projection.json', dropin)
        self.assertIn('systemctl restart live-infinita-autonomous-world.service', script)
        self.assertNotIn('systemctl restart live-infinita.service', script)
        self.assertNotIn('systemctl restart live-infinita-memoria-local.service', script)
        self.assertNotIn('systemctl restart live-infinita-renderer.service', script)
        self.assertIn('rollback()', script)
        self.assertIn('global_cap=48', script)


class FakeLedger:
    def active(self):
        return []


class FakeScheduler:
    def __init__(self) -> None:
        self.ledger = FakeLedger()

    def replan_all(self):
        return []


class FakeBuilder:
    def __init__(self) -> None:
        self.calls: list[int] = []

    def evaluate_tick(self, tick: int):
        self.calls.append(tick)
        return [{
            "tick": tick,
            "status": "created",
            "entity_id": "builder_test",
            "entity_type": "tree",
            "region_id": "r0",
            "role": "uplift",
            "projection_id": "ctp",
            "world_event_id": "evt",
            "mutation_decision_id": "dec",
        }]


class WorldTickBuilderIntegrationTests(unittest.TestCase):
    def test_world_builder_runs_after_authoritative_tick_and_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clock = SimulationClock(Path(tmp) / "clock.json")
            builder = FakeBuilder()
            runner = WorldTickRunner(
                clock,
                FakeScheduler(),
                world_builder_agent=builder,
            )
            result = runner.tick()
            self.assertEqual(builder.calls, [1])
            self.assertEqual(result["world_builder"][0]["entity_id"], "builder_test")
            self.assertEqual(result["world_builder"][0]["status"], "created")


if __name__ == "__main__":
    unittest.main()
