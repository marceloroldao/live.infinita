from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from autonomous_runtime import region_catalog_from_world
from npc_idle_wander import NpcIdleWander


class NovExploration007Test(unittest.TestCase):
    def setUp(self) -> None:
        topology = json.loads(
            (ROOT / "examples" / "nov-world-regions-005.json").read_text(encoding="utf-8")
        )
        self.catalog = region_catalog_from_world({"regions": topology["regions"]})
        scheduler = SimpleNamespace(planner=SimpleNamespace(regions=self.catalog))
        self.wander = NpcIdleWander(scheduler, npc_ids=["nov"])

    def test_deterministic_non_backtracking_walk_reaches_all_base_regions(self) -> None:
        entity = {
            "id": "nov",
            "region_id": "shelter",
            "properties": {},
        }
        visited = {"shelter"}
        transitions: list[tuple[str, str]] = []

        for crossing_index in range(24):
            bucket = 3 + crossing_index * 4
            current = entity["region_id"]
            region = self.wander._select_region(entity, bucket)
            self.assertIsNotNone(region)
            target = region.id
            previous = self.wander._previous_region(entity, current)
            if previous and len(self.catalog.get(current).neighbors) > 1:
                self.assertNotEqual(target, previous)
            transitions.append((current, target))
            if target != current:
                entity["properties"]["navigation"] = {
                    "previous_region_id": current,
                    "arrived_region_id": target,
                }
                entity["region_id"] = target
            visited.add(target)

        expected = {
            "clearing", "shelter", "deep_forest", "river_crossing", "village",
            "ridge", "waterfall_overlook", "watchtower", "stone_circle", "cave",
            "meadow", "ruins",
        }
        self.assertEqual(visited, expected, msg=str(transitions))

    def test_stale_navigation_pointer_is_ignored(self) -> None:
        entity = {
            "id": "nov",
            "region_id": "shelter",
            "properties": {
                "navigation": {
                    "previous_region_id": "clearing",
                    "arrived_region_id": "village",
                }
            },
        }
        self.assertEqual(self.wander._previous_region(entity, "shelter"), "")


if __name__ == "__main__":
    unittest.main()
