from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "apps" / "nov-sync" / "nov_sync_main.py"
spec = importlib.util.spec_from_file_location("nov_sync_main", ENTRY)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)

from packages.observability.nov_episode_delivery import DeliveryError


class NovSyncCliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.world = root / "world"
        self.world.mkdir()
        self.key = root / "device.pem"
        self.key.write_text("fake-private-key", encoding="utf-8")
        self.key.chmod(0o600)
        self.config = {
            "LIVE_INFINITA_NOV_SYNC_ENABLED": "1",
            "LIVE_INFINITA_NOV_SYNC_SERVER_URL": "https://memoria.invalid",
            "LIVE_INFINITA_NOV_SYNC_SERVER_ID": "central-server",
            "LIVE_INFINITA_NOV_SYNC_DEVICE_ID": "dev-live",
            "LIVE_INFINITA_NOV_SYNC_PRIVATE_KEY": str(self.key),
            "LIVE_INFINITA_NOV_SYNC_WORLD_DIR": str(self.world),
            "LIVE_INFINITA_NOV_SYNC_CHECKPOINT": str(root / "state" / "cursor.json"),
        }

    def test_fails_closed_without_explicit_enable_or_credentials(self):
        for conf in (
            {},
            {**self.config, "LIVE_INFINITA_NOV_SYNC_ENABLED": "0"},
            {**self.config, "LIVE_INFINITA_NOV_SYNC_DEVICE_ID": ""},
        ):
            with self.subTest(conf=conf.get("LIVE_INFINITA_NOV_SYNC_ENABLED")):
                with self.assertRaises(DeliveryError):
                    module.configured_session(conf)
        self.assertFalse((self.world.parent / "state").exists())

    def test_rejects_insecure_private_key_and_symlink(self):
        self.key.chmod(0o644)
        with self.assertRaises(DeliveryError):
            module.configured_session(self.config)
        self.key.chmod(0o600)
        shortcut = self.world.parent / "key-link"
        shortcut.symlink_to(self.key)
        with self.assertRaises(DeliveryError):
            module.configured_session({**self.config, "LIVE_INFINITA_NOV_SYNC_PRIVATE_KEY": str(shortcut)})

    def test_rejects_checkpoint_under_authoritative_world_tree(self):
        bad = self.world / "sync-state.json"
        with self.assertRaisesRegex(DeliveryError, "outside authoritative"):
            module.configured_session({**self.config, "LIVE_INFINITA_NOV_SYNC_CHECKPOINT": str(bad)})
        with self.assertRaises(DeliveryError):
            module.configured_session({**self.config, "LIVE_INFINITA_NOV_SYNC_CHECKPOINT": "relative.json"})

    def test_one_shot_has_hard_upper_bound_and_no_scheduler(self):
        for amount in (0, -1, 17):
            with self.assertRaises(DeliveryError):
                module.run_once(self.config, max_records=amount)
        with patch.object(module, "deliver_next", side_effect=[
            {"status": "acknowledged"}, {"status": "filtered_non_nov_record"},
            {"status": "waiting_complete_record"},
        ]) as delivery:
            status = module.run_once(self.config, max_records=16)
            self.assertEqual(status, {
                "mode": "one-shot-observational-sync", "acknowledged": 1,
                "filtered_non_nov_record": 1, "waiting_complete_record": 1,
            })
            self.assertEqual(delivery.call_count, 3)
        self.assertFalse((self.world.parent / "state").exists())
        self.assertNotIn("systemctl", ENTRY.read_text(encoding="utf-8"))
        self.assertNotIn("while True", ENTRY.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
