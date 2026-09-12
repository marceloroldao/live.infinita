from __future__ import annotations

import asyncio
import importlib
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "apps" / "sources"
if str(SOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCES_DIR))

bridge = importlib.import_module("tiktok_live_bridge")


class TikTokTransportTest(unittest.IsolatedAsyncioTestCase):
    def test_network_error_is_contained(self) -> None:
        with patch.object(
            bridge.urllib.request,
            "urlopen",
            side_effect=urllib.error.URLError("gateway offline"),
        ):
            status, result = bridge.post_json("http://127.0.0.1:9/event", {"x": 1}, 0.1)
        self.assertEqual(status, 0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["transport_error"], "URLError")

    async def test_async_transport_does_not_call_blocking_function_on_event_loop(self) -> None:
        caller_thread = None
        loop_thread = __import__("threading").get_ident()

        def fake_post(url, payload, timeout):
            nonlocal caller_thread
            caller_thread = __import__("threading").get_ident()
            return 200, {"ok": True}

        with patch.object(bridge, "post_json", side_effect=fake_post):
            status, result = await bridge.post_json_async("http://gateway", {"x": 1}, 1.0)
        self.assertEqual(status, 200)
        self.assertTrue(result["ok"])
        self.assertIsNotNone(caller_thread)
        self.assertNotEqual(caller_thread, loop_thread)


if __name__ == "__main__":
    unittest.main()
