from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

import autonomous_runtime_main as entry


class AutonomousRuntimeMainTest(unittest.TestCase):
    def test_npc_ids_are_canonicalized(self):
        with patch.dict(os.environ, {"LIVE_INFINITA_NPC_IDS": " nov,alice,nov , alice "}, clear=False):
            self.assertEqual(entry._npc_ids(), ["alice", "nov"])

    def test_missing_required_environment_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LIVE_INFINITA_DATA_DIR is required"):
                entry.build_from_environment()

    def test_invalid_tick_duration_fails_closed_before_build(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = {
                "LIVE_INFINITA_DATA_DIR": str(Path(tmpdir) / "data"),
                "LIVE_INFINITA_COLD_STORE_DIR": str(Path(tmpdir) / "cold"),
                "LIVE_INFINITA_COLD_BOOTSTRAP_FILE": str(Path(tmpdir) / "world.json"),
                "LIVE_INFINITA_NPC_IDS": "nov",
                "LIVE_INFINITA_TICK_DURATION_MS": "zero",
            }
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(RuntimeError, "must be an integer"):
                    entry.build_from_environment()


if __name__ == "__main__":
    unittest.main()
