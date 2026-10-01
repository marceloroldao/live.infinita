from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "structural_association_consolidator.py"
spec = importlib.util.spec_from_file_location("structural_association_consolidator_008y", MODULE_PATH)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StructuralAssociationConsolidator008YTests(unittest.TestCase):
    def test_bounded_success(self) -> None:
        def send(limit: int):
            self.assertEqual(limit, 2)
            return {
                "association_sync_observations": 2,
                "max_observations": 2,
                "associations": {
                    "pending_observations": 3,
                    "raw_observations": 56,
                    "derived_observations": 53,
                },
            }

        result = module.consolidate_once(2, send=send)
        self.assertEqual(
            result,
            {"replayed": 2, "pending": 3, "raw": 56, "derived": 53},
        )

    def test_inconsistent_cursor_is_rejected(self) -> None:
        def send(_limit: int):
            return {
                "association_sync_observations": 1,
                "max_observations": 2,
                "associations": {
                    "pending_observations": 4,
                    "raw_observations": 56,
                    "derived_observations": 51,
                },
            }

        with self.assertRaisesRegex(
            module.ConsolidationError,
            "sync_cursor_inconsistent",
        ):
            module.consolidate_once(2, send=send)

    def test_local_limit_is_guarded(self) -> None:
        with self.assertRaisesRegex(
            module.ConsolidationError,
            "max_observations_out_of_range",
        ):
            module.consolidate_once(17, send=lambda _limit: {})

    def test_endpoint_carries_bound(self) -> None:
        self.assertTrue(module._endpoint(2).endswith("?max_observations=2"))


if __name__ == "__main__":
    unittest.main()
