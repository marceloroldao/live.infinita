from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "broadcaster" / "broadcaster.py"
spec = importlib.util.spec_from_file_location("live_broadcaster", MODULE)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)
BroadcasterConfig = module.BroadcasterConfig
BroadcasterConfigError = module.BroadcasterConfigError
redact_url = module.redact_url
write_status = module.write_status


class BroadcasterCoreTest(unittest.TestCase):
    def config(self, **updates):
        data = dict(
            video_input="udp://127.0.0.1:5600",
            audio_input="udp://127.0.0.1:5500",
            output_url="rtmps://example.invalid/live/SECRET-STREAM-KEY",
        )
        data.update(updates)
        return BroadcasterConfig(**data)

    def test_defaults_are_native_portrait(self):
        config = self.config()
        self.assertEqual((config.width, config.height, config.fps), (720, 1280, 30))

    def test_command_maps_video_and_audio_and_uses_streaming_codecs(self):
        cmd = self.config().command()
        joined = " ".join(cmd)
        self.assertIn("-map 0:v:0", joined)
        self.assertIn("-map 1:a:0", joined)
        self.assertIn("-c:v libx264", joined)
        self.assertIn("-c:a aac", joined)
        self.assertIn("scale=720:1280", joined)
        self.assertIn("-f flv", joined)
        self.assertEqual(cmd[-1], "rtmps://example.invalid/live/SECRET-STREAM-KEY")

    def test_safe_command_never_prints_stream_key(self):
        text = self.config().safe_command_text()
        self.assertNotIn("SECRET-STREAM-KEY", text)
        self.assertIn("***", text)

    def test_probe_mode_never_contains_output_url(self):
        config = self.config()
        cmd = config.command(include_output=False, duration_seconds=5)
        self.assertNotIn(config.output_url, cmd)
        self.assertEqual(cmd[-3:], ["-f", "null", "-"])
        self.assertIn("-t", cmd)
        self.assertIn("5", cmd)

    def test_invalid_probe_duration_is_rejected(self):
        with self.assertRaises(BroadcasterConfigError):
            self.config().command(include_output=False, duration_seconds=0)

    def test_invalid_fps_is_rejected(self):
        with self.assertRaises(BroadcasterConfigError):
            self.config(fps=120).validate()

    def test_missing_video_input_is_rejected(self):
        with self.assertRaises(BroadcasterConfigError):
            self.config(video_input="").validate()

    def test_redact_url_hides_last_path_component_and_query(self):
        safe = redact_url("rtmps://host/app/key123?token=secret")
        self.assertEqual(safe, "rtmps://host/app/***?***")
        self.assertNotIn("key123", safe)
        self.assertNotIn("secret", safe)

    def test_status_file_is_atomic_and_never_contains_stream_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            with patch.dict(os.environ, {"LIVE_INFINITA_BROADCAST_STATUS": str(path)}):
                write_status("live", self.config(), mode="live", pid=123)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "live")
            self.assertEqual(payload["video"]["width"], 720)
            self.assertEqual(payload["video"]["height"], 1280)
            self.assertNotIn("SECRET-STREAM-KEY", path.read_text(encoding="utf-8"))
            self.assertIn("***", payload["destination"])


if __name__ == "__main__":
    unittest.main()
