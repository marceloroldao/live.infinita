from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"


class EnvironmentalDelivery008BETests(unittest.TestCase):
    def test_spatial_delivery_exposes_environment_outside_world_state(self) -> None:
        source = (RUNTIME / "main_spatial.py").read_text(encoding="utf-8")
        self.assertIn(
            'delivery["environmental_state"] = derive_environmental_state(',
            source,
        )
        self.assertIn('message["world"],', source)
        self.assertIn('_visual_environment_projection(projection)', source)
        self.assertIn('visual["regions"] = visual_regions', source)
        self.assertIn('visual["projection_id"] = visual_id', source)
        self.assertNotIn('message["world"]["environmental_state"]', source)
        self.assertNotIn('payload["world"]["environmental_state"]', source)

    def test_environment_rules_have_no_io_or_world_mutation_api(self) -> None:
        source = (RUNTIME / "environmental_rules.py").read_text(encoding="utf-8")
        self.assertNotIn("GuardedMutationService", source)
        self.assertNotIn("FileRegionColdStore", source)
        self.assertNotIn("Path(", source)
        self.assertNotIn(".write_text(", source)
        self.assertIn('"world_write_authority": False', source)
        self.assertIn('"memory_is_authority": False', source)

    def test_builder_requires_environment_before_candidates(self) -> None:
        source = (RUNTIME / "cognitive_world_builder.py").read_text(encoding="utf-8")
        derive = source.index("environmental_state = derive_environmental_state")
        candidate = source.index("candidates = self._candidate_specs")
        self.assertLess(derive, candidate)
        self.assertIn("environmental_regions", source)
        self.assertIn('"rock_exposure"', source)
        self.assertIn('"tree_suitability"', source)


if __name__ == "__main__":
    unittest.main()
