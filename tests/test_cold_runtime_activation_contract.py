from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from packages.spatial import FileRegionColdStore

ROOT = Path(__file__).resolve().parents[1]
MAIN_SPATIAL = ROOT / "apps" / "world-runtime" / "main_spatial.py"
COLD_ENGINE = ROOT / "apps" / "world-runtime" / "cold_engine.py"


class ColdRuntimeActivationContractTest(unittest.TestCase):
    def test_activation_is_explicit_and_requires_store_dir(self) -> None:
        source = MAIN_SPATIAL.read_text(encoding="utf-8")
        self.assertIn("LIVE_INFINITA_COLD_ENGINE", source)
        self.assertIn("LIVE_INFINITA_COLD_STORE_DIR", source)
        self.assertIn("_cold_engine_enabled()", source)
        self.assertIn("ColdAuthoritativeWorldEngine", source)
        self.assertNotIn("LIVE_INFINITA_COLD_ENGINE", source.split("def _cold_engine_enabled", 1)[0])

    def test_default_regional_bootstrap_is_explicit(self) -> None:
        source = MAIN_SPATIAL.read_text(encoding="utf-8")
        self.assertIn("world-state.mvp001.regional.bootstrap.json", source)
        bootstrap = ROOT / "examples" / "world-state.mvp001.regional.bootstrap.json"
        payload = json.loads(bootstrap.read_text(encoding="utf-8"))
        self.assertTrue(payload["regions"])
        self.assertTrue(all(entity.get("region_id") for entity in payload["entities"]))

    def test_cold_engine_source_is_fail_closed_for_legacy_world(self) -> None:
        source = COLD_ENGINE.read_text(encoding="utf-8")
        self.assertIn("requires a migrated cold-backed world.json", source)
        self.assertIn("requires an existing cold-store manifest", source)


if __name__ == "__main__":
    unittest.main()
