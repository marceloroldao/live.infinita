from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "apps" / "renderer-godot" / "materialization_transition.gd"
SCENE = ROOT / "apps" / "renderer-godot" / "main.tscn"


class MaterializationTransitionContractTest(unittest.TestCase):
    def test_transition_is_finite_and_lightweight(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("FADE_SECONDS", text)
        self.assertIn("visual.modulate.a", text)
        self.assertIn("START_SCALE_FACTOR", text)
        self.assertNotIn("load(", text)
        self.assertNotIn("preload(", text)
        self.assertNotIn("add_child", text)

    def test_warm_prediction_is_observed_before_cache_eviction(self) -> None:
        scene = SCENE.read_text(encoding="utf-8")
        promotion_index = scene.index('[node name="MaterializationTransition"')
        warm_index = scene.index('[node name="WarmPrefetch"')
        self.assertLess(promotion_index, warm_index)

    def test_metrics_distinguish_predicted_promotions(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("predicted_promotions_total", text)
        self.assertIn("active_transitions", text)


if __name__ == "__main__":
    unittest.main()
