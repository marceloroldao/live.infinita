from __future__ import annotations

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from packages.observability.runtime_metrics import (
    EventLoopLagMonitor, _bounded_json, _last_jsonl_record,
    _native_audio_metrics, recent_jsonl, runtime_snapshot,
)


class ManagerPerformanceTests(unittest.TestCase):
    def test_jsonl_tail_is_bounded_and_skips_partial_records(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "events.jsonl"
            path.write_text('{"event_identity":"one","text":"private"}\n'
                            '{"event_identity":"two","ok":true}\n'
                            '{"event_identity":"partial"', encoding="utf-8")
            self.assertEqual(_last_jsonl_record(path)["event_identity"], "two")
            self.assertEqual(_last_jsonl_record(path, limit=8), {})

    def test_recent_event_window_skips_partial_lines(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "world-events.jsonl"
            rows = [json.dumps({"sequence": n, "text": "x" * 80}) + "\n"
                    for n in range(200)]
            path.write_text("".join(rows) + '{"sequence": 999', encoding="utf-8")
            recent = recent_jsonl(path, max_bytes=1024, limit=5)
            self.assertEqual([row["sequence"] for row in recent], [195, 196, 197, 198, 199])
            self.assertEqual(recent_jsonl(path, max_bytes=0), [])
            self.assertEqual(recent_jsonl(path, limit=0), [])

    def test_large_sidecar_is_ignored(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "status.json"
            path.write_text('{"ok":true}', encoding="utf-8")
            self.assertEqual(_bounded_json(path)["ok"], True)
            self.assertEqual(_bounded_json(path, limit=2), {})

    def test_snapshot_exposes_only_operational_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / "audio"
            audio.mkdir()
            (root / "render-runtime-status.json").write_text(
                json.dumps({"updated_at_unix": __import__("time").time(),
                            "godot_fps": 12, "capture_fps": 15,
                            "governor_enabled": True, "token": "SHOULD_NOT_LEAK"}),
                encoding="utf-8")
            (audio / "status.json").write_text(
                '{"state":"connected","updated_at_unix":100,"last_narration":"PRIVATE TEXT","token":"HIDDEN"}',
                encoding="utf-8")
            (audio / "narration-events.jsonl").write_text(
                '{"event_identity":"cue-one","ok":true,"provider":"piper-local",'
                '"queued_pcm_bytes":2000,"text":"SECRET SPEECH"}\n', encoding="utf-8")
            (audio / "narration-cue-spool.jsonl").write_text(
                '{"cue":{"cue_id":"cue-one","text":"SECRET COMMENT"}}\n', encoding="utf-8")
            (audio / "native-metrics.txt").write_text(
                "voice_chunks=123\ndeadline_misses=9\nxruns=3\n", encoding="ascii")
            with patch("packages.observability.runtime_metrics._relay_health",
                       return_value={"available": True, "active_streams": 1, "max_clients": 4}):
                result = runtime_snapshot(root, {"last_ms": 2.5, "max_recent_ms": 11})
            self.assertTrue(result["renderer"]["available"])
            self.assertEqual(result["renderer"]["fps"], 12)
            self.assertEqual(result["audio"]["voice_chunks"], 123)
            self.assertEqual(result["audio"]["deadline_misses"], 9)
            self.assertEqual(result["audio"]["last_pcm_bytes"], 2000)
            self.assertEqual(result["audio_web"]["active_streams"], 1)
            self.assertEqual(result["api"]["max_recent_ms"], 11)
            serialized = json.dumps(result)
            for sensitive in ("SHOULD_NOT_LEAK", "PRIVATE TEXT", "HIDDEN",
                              "SECRET SPEECH", "SECRET COMMENT"):
                self.assertNotIn(sensitive, serialized)

    def test_stale_renderer_is_not_reported_as_available(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "render-runtime-status.json").write_text(
                '{"updated_at_unix":100,"godot_fps":12}', encoding="utf-8")
            with patch("packages.observability.runtime_metrics._relay_health",
                       return_value={"available": False}):
                self.assertFalse(runtime_snapshot(root, {})["renderer"]["available"])

    def test_native_metrics_reject_unbounded_data(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "metrics.txt"
            path.write_text("voice_chunks=123\nxruns=4\ndeadline_misses=5\nunknown=777\n", encoding="ascii")
            self.assertEqual(_native_audio_metrics(path), {"voice_chunks": 123, "xruns": 4, "deadline_misses": 5})
            path.write_text("x" * 9000, encoding="ascii")
            self.assertEqual(_native_audio_metrics(path), {})

    def test_loop_snapshot_is_bounded(self):
        monitor = EventLoopLagMonitor()
        for n in range(100):
            monitor.samples_ms.append(float(n))
        value = monitor.snapshot()
        self.assertEqual(value["samples"], 60)
        self.assertEqual(value["max_recent_ms"], 99.0)
        self.assertEqual(value["last_ms"], 99.0)

    def test_protected_route_and_manager_fields_are_wired(self):
        root = Path(__file__).resolve().parents[1]
        api = (root / "apps/world-runtime/main_cognitive_live.py").read_text(encoding="utf-8")
        html = (root / "apps/manager/index.html").read_text(encoding="utf-8")
        js = (root / "apps/manager/app.js").read_text(encoding="utf-8")
        self.assertIn('@app.get("/api/manage/performance", dependencies=[Depends(core.require_operator)])', api)
        self.assertIn('promote_api_route_before_root(app, "/api/manage/performance")', api)
        self.assertIn("async_runtime_snapshot(core.DATA_DIR, performance_loop)", api)
        self.assertIn('id="perf-voice"', html)
        self.assertIn('id="perf-fps"', html)
        self.assertIn("api('/api/manage/performance')", js)
        self.assertIn("void loadPerformance()", js)
        monitor_source = (root / "apps/world-runtime/main_live.py").read_text(encoding="utf-8")
        monitored = monitor_source.split("async def current_manager_monitor()", 1)[1].split("def _is_legacy_static_mount", 1)[0]
        self.assertNotIn("core.engine.verify_replay()", monitored)
        self.assertIn("core.STARTUP_REPLAY_OK", monitored)
        self.assertIn("recent_jsonl(core.engine.events_file", monitor_source)
        self.assertIn('"replay_check": "startup-cached"', monitor_source)


if __name__ == "__main__":
    unittest.main()
