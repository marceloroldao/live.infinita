from __future__ import annotations

import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from packages.narration_spool import append_cue, read_cues, resume_offset


class NarrationSpoolTests(unittest.TestCase):
    def test_append_read_and_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audio" / "narration-cue-spool.jsonl"
            first = {"cue_id": "cue:one", "text": "Primeira fala."}
            second = {"cue_id": "cue:two", "text": "Segunda fala."}
            append_cue(path, first)
            marker = resume_offset(path, "cue:one")
            append_cue(path, second)
            end, cues = read_cues(path, marker)
            self.assertEqual(cues, [second])
            self.assertEqual(end, path.stat().st_size)
            self.assertEqual(read_cues(path, end)[1], [])
            self.assertEqual(resume_offset(path, "missing"), path.stat().st_size)

    def test_partial_line_is_not_delivered(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spool.jsonl"
            path.write_bytes(b'{"cue":{"cue_id":"one","text":"Hi"}}')
            self.assertEqual(read_cues(path, 0), (0, []))
            with path.open("ab") as f:
                f.write(b"\n")
            self.assertEqual(read_cues(path, 0)[1], [{"cue_id":"one","text":"Hi"}])

    def test_rejects_invalid_and_oversized_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spool.jsonl"
            with self.assertRaises(ValueError):
                append_cue(path, {"cue_id": "", "text": "missing"})
            with self.assertRaises(ValueError):
                append_cue(path, {"cue_id": "large", "text": "A" * 5000})
            self.assertFalse(path.exists())

    def test_standalone_audio_entrypoint_imports_shared_spool(self):
        # The production unit starts stable_audio.py by path with no PYTHONPATH.
        # Running from a foreign cwd detects missing repository-root imports.
        audio_dir = Path(__file__).resolve().parents[1] / "apps" / "audio-service"
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory() as cwd:
            probe = subprocess.run(
                [sys.executable, "-c",
                 "import sys;sys.path.insert(0,sys.argv[1]);import retro_audio;"
                 "from packages.narration_spool import read_cues;print('AUDIO_IMPORT_OK')",
                 str(audio_dir)],
                cwd=cwd, env=env, capture_output=True, text=True, timeout=20,
            )
        self.assertEqual(probe.returncode, 0, probe.stderr)
        self.assertIn("AUDIO_IMPORT_OK", probe.stdout)

    def test_audio_service_recovers_cue_without_websocket(self):
        import server_audio
        import retro_audio

        class FakeAudio:
            def ambient_status(self):
                return {}

        async def check(path):
            with patch.object(server_audio, "AUDIO_DIR", path.parent), \
                 patch.object(server_audio, "write_status"), \
                 patch.object(server_audio, "persist_last_identity"), \
                 patch.object(server_audio, "load_last_identity", return_value=""):
                service = retro_audio.InteractionNarrationService(FakeAudio())
                task = asyncio.create_task(service.cue_spool_listener())
                try:
                    await asyncio.sleep(0.05)
                    append_cue(path, {"cue_id": "offline:1", "text": "Olá sem WebSocket.", "mode": "individual"})
                    identity, spoken = await asyncio.wait_for(service.queue.get(), 3.0)
                    self.assertEqual(identity, "offline:1")
                    self.assertEqual(spoken, "Olá sem WebSocket.")
                    service.queue.task_done()
                    await service.submit_narration_cue({"cue_id": "offline:1", "text": spoken})
                    self.assertTrue(service.queue.empty())
                finally:
                    service.stop.set()
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)

        with tempfile.TemporaryDirectory() as tmp:
            asyncio.run(check(Path(tmp) / "narration-cue-spool.jsonl"))


if __name__ == "__main__":
    unittest.main()
