from __future__ import annotations

from copy import deepcopy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from cognitive_shadow import CognitiveShadowRecorder, summarize_shadow_file  # noqa: E402
from shadow_world_tick import ShadowWorldTickRunner  # noqa: E402


class FakeStore:
    def __init__(self) -> None:
        self.entities = {
            "nov": {
                "id": "nov",
                "type": "human",
                "region_id": "clearing",
                "position": {"x": 640, "y": 360},
                "properties": {"needs": {"curiosity": 0.8, "safety": 0.2}},
            },
            "fire_01": {
                "id": "fire_01",
                "type": "campfire",
                "region_id": "clearing",
                "position": {"x": 700, "y": 405},
            },
            "shelter_marker": {
                "id": "shelter_marker",
                "type": "safe_place",
                "region_id": "shelter",
                "position": {"x": 900, "y": 375},
            },
            "ancient_tree": {
                "id": "ancient_tree",
                "type": "tree",
                "region_id": "deep_forest",
                "position": {"x": 320, "y": 335},
            },
        }

    def get_entity(self, entity_id: str):
        value = self.entities.get(entity_id)
        return deepcopy(value) if value is not None else None


class FakeRunner:
    def __init__(self, world: dict, store: FakeStore) -> None:
        self.world = world
        self.store = store
        self.clock = object()

    def tick(self):
        self.world["version"] += 1
        self.world["sequence"] += 1
        self.store.entities["nov"]["region_id"] = "shelter"
        self.store.entities["nov"]["position"] = {"x": 900, "y": 375}
        return {
            "advanced": True,
            "clock": {"tick": self.world["sequence"]},
            "plans": [{"plan_id": "plan-1", "actor_entity_id": "nov", "status": "completed"}],
            "npc_needs": [],
            "npc_strategies": [],
            "events": [],
            "conditional_events": [],
        }


class MemoriaV2ShadowModeTests(unittest.TestCase):
    def _world(self):
        return {
            "world_id": "nov-live-autonomous-001",
            "version": 10,
            "sequence": 20,
            "environment": {"period": "day", "weather": "clear", "biome": "forest"},
        }

    def test_shadow_records_best_candidate_without_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world = self._world()
            store = FakeStore()
            path = Path(directory) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path,
                world_provider=lambda: deepcopy(world),
                store=store,
                enabled=True,
            )
            wrapper = ShadowWorldTickRunner(FakeRunner(world, store), recorder)
            result = wrapper.tick()

            self.assertTrue(result["advanced"])
            self.assertEqual(result["cognitive_shadow"]["status"], "recorded")
            self.assertEqual(result["cognitive_shadow"]["best_candidate_action"], "nov_to_shelter")
            self.assertTrue(result["cognitive_shadow"]["exact_structural_match"])

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["world_mutated_by_shadow"])
            self.assertEqual(rows[0]["authority"], "shadow-observer")
            self.assertEqual(rows[0]["best_candidate"]["action"], "nov_to_shelter")
            self.assertTrue(rows[0]["best_candidate"]["exact_structural_match"])

            summary = summarize_shadow_file(path)
            self.assertEqual(summary["records"], 1)
            self.assertEqual(summary["exact_structural_matches"], 1)
            self.assertEqual(summary["exact_match_rate"], 1.0)

    def test_disabled_shadow_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            world = self._world()
            store = FakeStore()
            path = Path(directory) / "shadow.jsonl"
            recorder = CognitiveShadowRecorder(
                path,
                world_provider=lambda: deepcopy(world),
                store=store,
                enabled=False,
            )
            before = deepcopy(world)
            self.assertIsNone(recorder.begin_tick())
            self.assertEqual(world, before)
            self.assertFalse(path.exists())

    def test_shadow_failure_never_blocks_authoritative_tick(self) -> None:
        class BrokenRecorder:
            enabled = True

            def begin_tick(self):
                raise RuntimeError("shadow unavailable")

            def complete_tick(self, token, result):
                raise AssertionError("must not be called after begin failure")

        world = self._world()
        store = FakeStore()
        wrapper = ShadowWorldTickRunner(FakeRunner(world, store), BrokenRecorder())
        result = wrapper.tick()
        self.assertTrue(result["advanced"])
        self.assertEqual(world["version"], 11)
        self.assertEqual(result["cognitive_shadow"]["status"], "begin_error")
        self.assertEqual(result["cognitive_shadow"]["error_type"], "RuntimeError")
        self.assertFalse(result["cognitive_shadow"]["world_mutated_by_shadow"])

    def test_deployment_keeps_shadow_disabled_by_default(self) -> None:
        env_example = (ROOT / "deploy" / "autonomous-world.env.example").read_text(encoding="utf-8")
        runtime_main = (ROOT / "apps" / "world-runtime" / "autonomous_runtime_main.py").read_text(encoding="utf-8")
        api = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")

        self.assertIn("LIVE_INFINITA_MEMORIA_V2_SHADOW=0", env_example)
        self.assertIn('LIVE_INFINITA_MEMORIA_V2_SHADOW', runtime_main)
        self.assertIn('"selection_authority": False', api)
        self.assertIn('"direct_world_write": False', api)
        self.assertIn('/api/cognitive/v2/shadow/metrics', api)


if __name__ == "__main__":
    unittest.main()
