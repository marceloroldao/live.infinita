from __future__ import annotations

import unittest

from packages.spatial import InterestConfig, SpatialResolver


class SpatialResolverTest(unittest.TestCase):
    def test_near_entities_are_hot_and_far_entities_omitted(self):
        resolver = SpatialResolver(InterestConfig(hot_radius=100, warm_radius=250))
        result = resolver.resolve(
            observer={"position": {"x": 0, "y": 0}},
            direction={"x": 1, "y": 0},
            entities=[
                {"id": "near", "position": {"x": 60, "y": 0}},
                {"id": "warm", "position": {"x": 180, "y": 0}},
                {"id": "far", "position": {"x": 500, "y": 0}},
            ],
        )
        self.assertEqual(result["hot"]["entity_ids"], ["near"])
        self.assertEqual(result["warm"]["entity_ids"], ["warm"])
        self.assertNotIn("far", result["hot"]["entity_ids"] + result["warm"]["entity_ids"])
        self.assertTrue(result["cold_omitted"])

    def test_direction_bias_prefers_entities_ahead(self):
        resolver = SpatialResolver(InterestConfig(hot_radius=10, warm_radius=300, max_warm_entities=1))
        result = resolver.resolve(
            observer={"position": {"x": 0, "y": 0}},
            direction={"x": 1, "y": 0},
            entities=[
                {"id": "ahead", "position": {"x": 150, "y": 0}},
                {"id": "behind", "position": {"x": -150, "y": 0}},
            ],
        )
        self.assertEqual(result["warm"]["entity_ids"], ["ahead"])

    def test_semantic_importance_can_raise_priority_without_forcing_hot(self):
        resolver = SpatialResolver(InterestConfig(hot_radius=50, warm_radius=300, max_warm_entities=1))
        result = resolver.resolve(
            observer={"position": {"x": 0, "y": 0}},
            entities=[
                {"id": "ordinary", "position": {"x": 120, "y": 0}},
                {"id": "story", "position": {"x": 180, "y": 0}, "properties": {"importance": 1.0}},
            ],
        )
        self.assertEqual(result["warm"]["entity_ids"], ["story"])
        self.assertEqual(result["hot"]["entity_ids"], [])

    def test_region_sets_use_region_radius_plus_interest_radius(self):
        resolver = SpatialResolver(InterestConfig(hot_radius=100, warm_radius=300))
        result = resolver.resolve(
            observer={"position": {"x": 0, "y": 0}},
            entities=[],
            regions=[
                {"id": "forest", "center": {"x": 80, "y": 0}, "radius": 30},
                {"id": "field", "center": {"x": 250, "y": 0}, "radius": 20},
                {"id": "city", "center": {"x": 900, "y": 0}, "radius": 80},
            ],
        )
        self.assertEqual(result["hot"]["region_ids"], ["forest"])
        self.assertEqual(result["warm"]["region_ids"], ["field"])
        self.assertNotIn("city", result["hot"]["region_ids"] + result["warm"]["region_ids"])

    def test_output_order_is_deterministic(self):
        resolver = SpatialResolver(InterestConfig(hot_radius=10, warm_radius=300))
        entities = [
            {"id": "b", "position": {"x": 100, "y": 100}},
            {"id": "a", "position": {"x": 100, "y": -100}},
        ]
        first = resolver.resolve(observer={"position": {"x": 0, "y": 0}}, entities=entities)
        second = resolver.resolve(observer={"position": {"x": 0, "y": 0}}, entities=list(reversed(entities)))
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
