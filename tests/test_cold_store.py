from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from packages.spatial import (
    ColdRegionCandidateCache,
    FileRegionColdStore,
    SpatialResolver,
    externalize_world_entities,
)


class ColdStoreTest(unittest.TestCase):
    def _entities(self, regions: int = 64, per_region: int = 20):
        rows = []
        for r in range(regions):
            for i in range(per_region):
                rows.append({
                    "id": f"e_{r:04d}_{i:03d}",
                    "type": "tree",
                    "region_id": f"r_{r:04d}",
                    "position": {"x": r * 300.0 + i, "y": 0.0},
                    "properties": {"seed": r * 1000 + i},
                })
        return rows

    def test_externalization_removes_full_entity_payloads_from_world(self):
        with TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp))
            world = {"world_id": "cold", "entities": self._entities(8, 10), "regions": []}
            cold_world = externalize_world_entities(world, store)
            self.assertEqual(cold_world["entities"], [])
            self.assertEqual(cold_world["cold_entities"]["entities_total"], 80)
            self.assertEqual(cold_world["cold_entities"]["payload_resident_entities"], 0)
            self.assertEqual(store.stats()["payload_resident_entities"], 0)
            self.assertEqual(len(world["entities"]), 80)

    def test_region_payloads_survive_store_reopen(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = FileRegionColdStore(root)
            first.replace_all(self._entities(6, 7))
            reopened = FileRegionColdStore(root)
            self.assertEqual(reopened.entities_total(), 42)
            rows = reopened.load_region("r_0003")
            self.assertEqual(len(rows), 7)
            self.assertTrue(all(row["region_id"] == "r_0003" for row in rows))

    def test_candidate_cache_is_bounded_while_store_grows(self):
        with TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp))
            store.replace_all(self._entities(256, 20))
            cache = ColdRegionCandidateCache(store, max_regions=3)

            for center in (3, 80, 160, 220):
                region_ids = [f"r_{center - 1:04d}", f"r_{center:04d}", f"r_{center + 1:04d}"]
                result = cache.candidates(region_ids)
                self.assertLessEqual(len(result["resident_regions"]), 3)
                self.assertLessEqual(result["resident_payload_entities"], 60)
                self.assertEqual(result["store_entities_total"], 5120)
                self.assertEqual(result["candidates_examined"], 60)

    def test_cold_to_local_resolution_hydrates_only_requested_regions(self):
        with TemporaryDirectory() as tmp:
            store = FileRegionColdStore(Path(tmp))
            store.replace_all(self._entities(128, 20))
            cache = ColdRegionCandidateCache(store, max_regions=3)
            region_ids = ["r_0063", "r_0064", "r_0065"]
            query = cache.candidates(region_ids)

            resolved = SpatialResolver().resolve(
                observer={"position": {"x": 64 * 300.0, "y": 0.0}},
                direction={"x": 1.0, "y": 0.0},
                entities=query["entities"],
                regions=[],
            )
            self.assertTrue(resolved["cold_omitted"])
            self.assertLessEqual(len(resolved["hot"]["entity_ids"]), 96)
            self.assertLessEqual(len(resolved["warm"]["entity_ids"]), 192)
            self.assertEqual(query["store_entities_total"], 2560)
            self.assertLessEqual(query["resident_payload_entities"], 60)


if __name__ == "__main__":
    unittest.main()
