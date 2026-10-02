from __future__ import annotations

import importlib.util
import json
import tempfile
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
CpuPressureGovernor = module.CpuPressureGovernor
HeadlessRenderer = module.HeadlessRenderer


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

    def test_explicit_scene_is_appended_without_changing_default(self):
        default = HeadlessRendererConfig().godot_command()
        self.assertNotIn("res://world_map_preview.tscn", default)
        cfg = HeadlessRendererConfig(scene="res://world_map_preview.tscn")
        command = cfg.godot_command()
        self.assertEqual(command[-1], "res://world_map_preview.tscn")
        with self.assertRaises(RendererConfigError):
            HeadlessRendererConfig(scene="../bad.tscn").validate()

    def test_capture_is_video_only_local_udp_mpegts(self):
        cfg = HeadlessRendererConfig()
        command = cfg.capture_command("ffmpeg")
        text = " ".join(command)
        self.assertIn("x11grab", command)
        self.assertIn("-an", command)
        self.assertIn("libx264", command)
        self.assertIn("mpegts", command)
        self.assertIn("720x1280", command)
        self.assertNotIn("-vf", command)
        self.assertIn("udp://127.0.0.1:5600", text)

    def test_internal_render_scale_preserves_output_resolution(self):
        cfg = HeadlessRendererConfig(
            width=720,
            height=1280,
            internal_width=432,
            internal_height=768,
        )
        self.assertIn("432x768x24", cfg.xvfb_command("Xvfb"))
        self.assertIn("432x768", cfg.godot_command())
        command = cfg.capture_command("ffmpeg")
        self.assertIn("432x768", command)
        self.assertIn("-vf", command)
        self.assertIn("scale=720:1280:flags=fast_bilinear", command)
        with self.assertRaises(RendererConfigError):
            HeadlessRendererConfig(
                internal_width=432,
                internal_height=1000,
            ).validate()

    def test_native_video_bus_skips_early_upscale(self):
        cfg = HeadlessRendererConfig(
            width=720,
            height=1280,
            internal_width=432,
            internal_height=768,
            native_bus_resolution=True,
        )
        command = cfg.capture_command("ffmpeg")
        self.assertIn("432x768", command)
        self.assertNotIn("-vf", command)
        self.assertEqual((cfg.bus_width, cfg.bus_height), (432, 768))

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

    def test_pressure_parser_and_bounded_degradation(self):
        pressure = "some avg10=66.73 avg60=50.12 avg300=42.00 total=900\nfull avg10=0.00"
        self.assertEqual(CpuPressureGovernor.pressure_avg10(pressure), 66.73)
        self.assertIsNone(CpuPressureGovernor.pressure_avg10("full avg10=1.00"))
        governor = CpuPressureGovernor(max_fps=20, min_fps=12, recovery_samples=3)
        self.assertEqual(governor.update(56), 12)
        self.assertEqual(governor.update(None), 12)
        self.assertEqual(governor.update(0), 12)
        self.assertEqual(governor.update(0), 12)
        self.assertEqual(governor.update(0), 14)
        self.assertEqual(governor.update(40), 14)
        self.assertEqual(governor.update(56), 12)
        self.assertEqual(governor.update(40), 12)
        self.assertEqual(governor.update(40), 12)
        self.assertEqual(governor.update(40), 14)

    def test_governor_file_is_private_and_disabled_by_default(self):
        cfg = HeadlessRendererConfig()
        self.assertFalse(cfg.cpu_governor_enabled)
        renderer = HeadlessRenderer(cfg)
        env = {}
        renderer._start_governor(env)
        self.assertEqual(env, {})
        enabled = HeadlessRenderer(HeadlessRendererConfig(cpu_governor_enabled=True))
        try:
            enabled._start_governor(env)
            path = Path(env["LIVE_INFINITA_RENDER_CONTROL_FILE"])
            self.assertEqual(path.read_text(), "20\n")
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)
            enabled._publish_fps(12)
            self.assertEqual(path.read_text(), "12\n")
        finally:
            enabled.stop()
        self.assertFalse(path.exists())

    def test_renderer_emits_bounded_operational_status(self):
        with tempfile.TemporaryDirectory() as directory:
            renderer = HeadlessRenderer(HeadlessRendererConfig(
                fps=15, godot_fps=20, minimum_godot_fps=12,
                cpu_governor_enabled=True))
            renderer._status_file = Path(directory) / "renderer.json"
            renderer._fps_governor.current_fps = 12
            renderer._publish_status(60.5)
            status = json.loads(renderer._status_file.read_text())
            self.assertEqual(status["godot_fps"], 12)
            self.assertEqual(status["capture_fps"], 15)
            self.assertEqual(status["render_width"], 720)
            self.assertEqual(status["render_height"], 1280)
            self.assertEqual(status["output_width"], 720)
            self.assertEqual(status["output_height"], 1280)
            self.assertEqual(status["bus_width"], 720)
            self.assertEqual(status["bus_height"], 1280)
            self.assertFalse(status["native_bus_resolution"])
            self.assertEqual(status["cpu_pressure_avg10_pct"], 60.5)
            self.assertTrue(status["governor_enabled"])
            self.assertEqual(status["scene"], "project-default")
            self.assertEqual(set(status), {
                "updated_at_unix", "godot_fps", "capture_fps",
                "render_width", "render_height", "output_width", "output_height",
                "bus_width", "bus_height", "native_bus_resolution",
                "governor_enabled", "cpu_pressure_avg10_pct", "scene"})
            renderer.stop()

    def test_native_godot_polls_control_but_browser_export_is_unchanged(self):
        scene = (ROOT / "apps" / "renderer-godot" / "main.gd").read_text(encoding="utf-8")
        preview = (ROOT / "apps" / "renderer-godot" / "world_map_preview.gd").read_text(encoding="utf-8")
        unit = (ROOT / "deploy" / "live-infinita-renderer.service").read_text(encoding="utf-8")
        self.assertIn('if OS.has_feature("web"):', scene)
        self.assertIn('Engine.max_fps = target_fps', scene)
        self.assertIn('if OS.has_feature("web"):', preview)
        self.assertIn('OS.get_environment("LIVE_INFINITA_RENDER_CONTROL_FILE")', preview)
        self.assertIn('Engine.max_fps = target_fps', preview)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_CPU_GOVERNOR=1', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_NATIVE_BUS=1', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_FPS=15', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_INTERNAL_WIDTH=432', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_INTERNAL_HEIGHT=768', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_GODOT_FPS=15', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_GODOT_MIN_FPS=8', unit)
        self.assertIn('Environment=LIVE_INFINITA_RENDER_SCENE=res://world_map_preview.tscn', unit)
        self.assertIn('Nice=5', unit)



if __name__ == "__main__":
    unittest.main()
