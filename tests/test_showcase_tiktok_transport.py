from __future__ import annotations

import asyncio
import importlib
import sys
import tempfile
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


class TikTokLifecycleTest(unittest.TestCase):
    def _config(self, status_file: Path) -> bridge.BridgeConfig:
        return bridge.BridgeConfig(
            unique_id="@liveinfinita",
            gateway_url="http://127.0.0.1:8080/api/source/tiktok/event",
            audience_url="http://127.0.0.1:8080/api/audience/tiktok/event",
            retry_seconds=30.0,
            status_file=status_file,
        )

    def test_clean_disconnect_exits_for_systemd_restart_without_sleep_loop(self) -> None:
        class Client:
            def run(self):
                return None

        with tempfile.TemporaryDirectory() as directory:
            config = self._config(Path(directory) / "status.json")
            with (
                patch.object(bridge.BridgeConfig, "from_env", return_value=config),
                patch.object(bridge, "build_client", return_value=Client()),
                patch.object(bridge.time, "sleep", side_effect=AssertionError("bridge must not self-retry")),
            ):
                result = bridge.main()

        self.assertEqual(result, bridge.RESTART_EXIT_CODE)

    def test_connection_error_exits_for_clean_restart(self) -> None:
        class Client:
            def run(self):
                raise RuntimeError("live unavailable")

        with tempfile.TemporaryDirectory() as directory:
            status_file = Path(directory) / "status.json"
            config = self._config(status_file)
            with (
                patch.object(bridge.BridgeConfig, "from_env", return_value=config),
                patch.object(bridge, "build_client", return_value=Client()),
                patch.object(bridge.time, "sleep", side_effect=AssertionError("bridge must not self-retry")),
            ):
                result = bridge.main()
            status = __import__("json").loads(status_file.read_text(encoding="utf-8"))

        self.assertEqual(result, bridge.RESTART_EXIT_CODE)
        self.assertEqual(status["state"], "waiting_retry")
        self.assertEqual(status["error_type"], "RuntimeError")

    def test_systemd_owns_retry_delay_and_file_descriptor_limit(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita-tiktok.service").read_text(encoding="utf-8")
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("RestartSec=30", unit)
        self.assertIn("LimitNOFILE=65536", unit)


if __name__ == "__main__":
    unittest.main()
