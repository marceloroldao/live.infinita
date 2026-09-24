from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


renderer = load_module("media_contract_renderer", ROOT / "apps" / "headless-renderer" / "headless_renderer.py")
broadcaster = load_module("media_contract_broadcaster", ROOT / "apps" / "broadcaster" / "broadcaster.py")


class MediaBusContractTest(unittest.TestCase):
    def test_renderer_video_bus_matches_broadcaster_default_input(self):
        render_cfg = renderer.HeadlessRendererConfig()
        broadcast_cfg = broadcaster.BroadcasterConfig.from_env()
        render_url = urlsplit(render_cfg.video_output)
        input_url = urlsplit(broadcast_cfg.video_input)
        self.assertEqual(render_url.hostname, "127.0.0.1")
        self.assertEqual(input_url.hostname, "127.0.0.1")
        self.assertEqual(render_url.port, input_url.port)
        self.assertEqual(render_url.port, 5600)

    def test_audio_bus_is_local_and_separate_from_video(self):
        broadcast_cfg = broadcaster.BroadcasterConfig.from_env()
        video_url = urlsplit(broadcast_cfg.video_input)
        audio_url = urlsplit(broadcast_cfg.audio_input)
        self.assertEqual(video_url.hostname, "127.0.0.1")
        self.assertEqual(audio_url.hostname, "127.0.0.1")
        self.assertEqual(video_url.port, 5600)
        self.assertEqual(audio_url.port, 5500)
        self.assertNotEqual(video_url.port, audio_url.port)

    def test_broadcaster_requires_external_output_even_with_local_buses(self):
        cfg = broadcaster.BroadcasterConfig.from_env()
        self.assertEqual(cfg.output_url, "")
        with self.assertRaises(broadcaster.BroadcasterConfigError):
            cfg.validate(require_output=True)
        cfg.validate(require_output=False)


if __name__ == "__main__":
    unittest.main()
