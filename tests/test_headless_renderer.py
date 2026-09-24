from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "headless-renderer" / "headless_renderer.py"
spec = importlib.util.spec_from_file_location("headless_renderer", MODULE)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)
HeadlessRendererConfig = module.HeadlessRendererConfig
RendererConfigError = module.RendererConfigError


class HeadlessRendererConfigTest(unittest.TestCase):
    def test_godot_runs_native_x11_at_expected_resolution(self):
        cfg = HeadlessRendererConfig()
        command = cfg.godot_command()
        self.assertEqual(command[0], cfg.godot_bin)
        self.assertIn("--display-driver", command)
        self.assertIn("x11", command)
        self.assertIn("--resolution", command)
        self.assertIn("720x1280", command)
        self.assertEqual((cfg.width, cfg.height), (720, 1280))
        self.assertIn(cfg.project_dir, command)

    def test_capture_is_video_only_local_udp_mpegts(self):
        cfg = HeadlessRendererConfig()
        command = cfg.capture_command("ffmpeg")
        text = " ".join(command)
        self.assertIn("x11grab", command)
        self.assertIn("-an", command)
        self.assertIn("libx264", command)
        self.assertIn("mpegts", command)
        self.assertIn("720x1280", command)
        self.assertIn("udp://127.0.0.1:5600", text)

    def test_xvfb_does_not_listen_on_tcp(self):
        cfg = HeadlessRendererConfig()
        command = cfg.xvfb_command("Xvfb")
        self.assertIn("720x1280x24", command)
        self.assertIn("-nolisten", command)
        self.assertIn("tcp", command)

    def test_invalid_remote_video_bus_is_rejected(self):
        cfg = HeadlessRendererConfig(video_output="udp://10.0.0.9:5600")
        with self.assertRaises(RendererConfigError):
            cfg.validate()

    def test_rtmp_video_bus_is_rejected(self):
        cfg = HeadlessRendererConfig(video_output="rtmp://example.invalid/live")
        with self.assertRaises(RendererConfigError):
            cfg.validate()


if __name__ == "__main__":
    unittest.main()
