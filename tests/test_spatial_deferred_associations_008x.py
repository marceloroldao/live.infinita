from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "nov_spatial_memory_sync.py"
spec = importlib.util.spec_from_file_location("nov_spatial_memory_sync_008x", MODULE_PATH)
assert spec and spec.loader
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


class SpatialDeferredAssociations008XTests(unittest.TestCase):
    @staticmethod
    def payload() -> dict:
        return {
            "event": {
                "version": 1,
                "source_id": "live:test",
                "sequence": 1,
                "byte_offset": 0,
                "byte_length": 1,
                "trail": [1, 2],
                "relation_ids": [],
                "signature": "0000000000000001",
                "resolution": 2,
            }
        }

    def test_endpoint_requires_deferred_association_mode(self) -> None:
        self.assertTrue(sync.ENDPOINT.endswith("?defer_associations=true"))

    def test_ack_requires_explicit_deferred_confirmation(self) -> None:
        payload = self.payload()
        base = {
            "stored": True,
            "duplicate": False,
            "observation_id": sync._observation_id(payload["event"]),
            "semantic_projection": False,
            "backend": "sqlite",
        }
        with self.assertRaisesRegex(
            sync.SpatialMemorySyncError,
            "structural_ack_mismatch",
        ):
            sync._validate_ack(base, payload)

        deferred = dict(base)
        deferred["association_sync_deferred"] = True
        sync._validate_ack(deferred, payload)


if __name__ == "__main__":
    unittest.main()
