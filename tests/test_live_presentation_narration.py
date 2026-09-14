from pathlib import Path
import unittest

from packages.spatial.resolver import InterestConfig


ROOT = Path(__file__).resolve().parents[1]


class LivePresentationNarrationTests(unittest.TestCase):
    def test_showcase_hot_radius_keeps_clearing_visible_from_shelter(self) -> None:
        config = InterestConfig()
        self.assertGreaterEqual(config.hot_radius, 260.0)
        self.assertLess(config.hot_radius, config.warm_radius)

    def test_plan_scheduler_does_not_publish_plan_debug_as_narration(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "plan_scheduler.py").read_text(encoding="utf-8")
        self.assertNotIn('narration=f"plan {plan_id}', source)
        self.assertIn("_public_narration", source)

    def test_public_stream_filters_legacy_plan_debug(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_live.py").read_text(encoding="utf-8")
        self.assertIn("_looks_internal_narration", source)
        self.assertIn("Nov continua sua jornada pelo mundo.", source)


if __name__ == "__main__":
    unittest.main()
