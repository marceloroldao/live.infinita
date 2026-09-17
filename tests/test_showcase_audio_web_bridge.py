from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "audio-web-bridge" / "audio_web_bridge.py"
spec = importlib.util.spec_from_file_location("audio_web_bridge", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)


class AudioWebBridgeTest(unittest.IsolatedAsyncioTestCase):
    def test_ffmpeg_command_buffers_and_repairs_audio_jitter(self) -> None:
        command = module.build_ffmpeg_command()
        self.assertEqual(command[0], module.FFMPEG_BIN)
        self.assertIn(module.UDP_INPUT, command)
        self.assertIn("libmp3lame", command)
        self.assertIn("48000", command)
        self.assertIn("128k", command)
        self.assertIn("4096", command)
        self.assertIn("aresample=async=1000:first_pts=0", command)
        self.assertNotIn("nobuffer", command)
        self.assertNotIn("low_delay", command)
        self.assertEqual(command[-2:], ["mp3", "pipe:1"])

    async def test_health_exposes_real_input_capacity_and_continuity_policy(self) -> None:
        with patch.object(module, "ffmpeg_available", return_value=True):
            response = await module.health()
        self.assertEqual(response.status_code, 200)
        body = response.body.decode("utf-8")
        self.assertIn(module.UDP_INPUT, body)
        self.assertIn('"ffmpeg_available":true', body)
        self.assertIn('"openai_audio":false', body)
        self.assertIn('"transport_buffered":true', body)
        self.assertIn('"jitter_filter":"aresample-async"', body)
        self.assertIn('"latency_policy":"continuity-first"', body)

    async def test_health_fails_when_ffmpeg_is_missing(self) -> None:
        with patch.object(module, "ffmpeg_available", return_value=False):
            response = await module.health()
        self.assertEqual(response.status_code, 503)
        self.assertIn('"ok":false', response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
