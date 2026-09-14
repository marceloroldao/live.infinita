from __future__ import annotations

from copy import deepcopy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "memoria_v2_adapter.py"
spec = importlib.util.spec_from_file_location("memoria_v2_adapter", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class MemoriaV2CognitiveProjectionTests(unittest.TestCase):
    def _world(self):
        return {
            "world_id": "nov-live-autonomous-001",
            "version": 12,
            "sequence": 44,
            "state_hash": "world-hash-44",
            "environment": {"period": "night", "weather": "clear", "biome": "forest"},
        }

    def _entities(self):
        nov = {
            "id": "nov",
            "type": "human",
            "region_id": "clearing",
            "position": {"x": 640, "y": 360},
            "properties": {
                "needs": {"safety": 0.20, "energy": 0.86, "curiosity": 0.74},
            },
        }
        targets = {
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
        return nov, targets

    def test_frame_is_deterministic_read_only_and_exposes_four_nov_interventions(self) -> None:
        world = self._world()
        nov, targets = self._entities()
        before_world = deepcopy(world)
        before_nov = deepcopy(nov)
        before_targets = deepcopy(targets)

        frame = module.build_nov_cognitive_frame(
            world=world,
            observer=nov,
            targets=targets,
            context_digest="ctx-44",
        )
        repeated = module.build_nov_cognitive_frame(
            world=world,
            observer=nov,
            targets=targets,
            context_digest="ctx-44",
        )

        self.assertEqual(frame, repeated)
        self.assertEqual(len(frame.available_interventions), 4)
        self.assertEqual(len(frame.candidate_outcomes), 4)
        self.assertEqual(frame.provenance["authority"], "read-only-cognitive-projection")
        self.assertEqual(frame.provenance["context_digest"], "ctx-44")
        self.assertIn("live:entity:nov", frame.state_addresses)
        self.assertIn("live:region:clearing", frame.state_addresses)
        self.assertIn("live:need:curiosity:high", frame.state_addresses)
        self.assertEqual(world, before_world)
        self.assertEqual(nov, before_nov)
        self.assertEqual(targets, before_targets)

    def test_shelter_candidate_predicts_structural_region_change_without_committing_it(self) -> None:
        world = self._world()
        nov, targets = self._entities()
        frame = module.build_nov_cognitive_frame(
            world=world,
            observer=nov,
            targets=targets,
        )
        intervention = next(
            item for item in frame.available_interventions if item.action == "nov_to_shelter"
        )
        candidate = next(
            item for item in frame.candidate_outcomes
            if item.proposal_id == intervention.proposal_id
        )

        self.assertIn("live:region:shelter", candidate.next_state_addresses)
        self.assertIn("live:near:shelter_marker", candidate.next_state_addresses)
        self.assertIn("live:action:nov_to_shelter", candidate.next_state_addresses)
        self.assertNotIn("live:region:clearing", candidate.next_state_addresses)
        self.assertEqual(nov["region_id"], "clearing")

    def test_memoria_request_contract_selects_exactly_one_intervention(self) -> None:
        world = self._world()
        nov, targets = self._entities()
        frame = module.build_nov_cognitive_frame(
            world=world,
            observer=nov,
            targets=targets,
        )
        intervention = frame.available_interventions[0]
        payload = module.to_memoria_v2_request_payload(
            frame,
            proposal_id=intervention.proposal_id,
        )

        self.assertEqual(payload["frame_id"], frame.frame_id)
        self.assertEqual(payload["intervention_id"], intervention.proposal_id)
        self.assertEqual(payload["intervention_address"], intervention.intervention_address)
        self.assertEqual(payload["provenance"], "live.infinita")
        self.assertEqual(len(payload["candidates"]), 1)

    def test_cognitive_runtime_is_staged_disabled_and_read_only(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
        wrapper = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")
        adapter = MODULE_PATH.read_text(encoding="utf-8")

        self.assertIn('LIVE_INFINITA_MEMORIA_V2_COGNITIVE_GYM=0', unit)
        self.assertIn('"world_mutated": False', wrapper)
        self.assertIn('"direct_world_write": False', wrapper)
        self.assertNotIn("commit_action(", adapter)
        self.assertNotIn("commit_mutation(", adapter)


if __name__ == "__main__":
    unittest.main()
