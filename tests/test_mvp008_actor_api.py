from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "world-runtime"))


class ActorAPITest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        with patch.dict(os.environ, {"LIVE_INFINITA_DATA_DIR": self.tmp.name}):
            spec = importlib.util.spec_from_file_location("actor_test_runtime", ROOT / "apps/world-runtime/main.py")
            self.runtime = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = self.runtime
            self.addCleanup(sys.modules.pop, spec.name, None)
            spec.loader.exec_module(self.runtime)
        self.client = TestClient(self.runtime.app)
        self.addCleanup(self.client.close)

    def test_audience_and_rejected_comment_observe_without_world_mutation(self):
        before = self.client.get("/api/world").json()
        event = {"source_event_id": "join-1", "actor_id": "alice", "display_name": "Alice", "kind": "join"}
        for source in ("tiktok", "youtube"):
            self.assertEqual(self.client.post(f"/api/audience/{source}/event", json=event).status_code, 202)
        retry = self.client.post("/api/audience/tiktok/event", json=event)
        self.assertTrue(retry.json()["duplicate"])
        comment = {"source_event_id": "comment-1", "actor_id": "alice", "display_name": "Alice 2", "text": "hello everyone"}
        self.assertEqual(self.client.post("/api/source/tiktok/event", json=comment).status_code, 422)
        actor = self.client.get("/api/actors/tiktok/alice").json()
        self.assertEqual(actor["interactions_by_kind"], {"join": 1, "text": 1})
        self.assertEqual(actor["display_name"], "Alice 2")
        self.assertIsNone(actor["entity_id"])
        self.assertEqual(self.client.get("/api/actors").json()["observations_total"], 3)
        self.assertEqual(self.client.get("/api/actors/youtube/alice").json()["interactions_total"], 1)
        self.assertEqual(self.client.get("/api/actors/tiktok/missing").status_code, 404)
        self.assertEqual(self.client.get("/api/world").json(), before)
        self.assertTrue(self.client.get("/api/replay/verify").json()["ok"])

    def test_backfill_is_idempotent_and_preserves_world_files(self):
        runtime = self.runtime
        runtime.append_jsonl(runtime.AUDIENCE_EVENTS_FILE, {
            "source": "tiktok", "source_event_id": "historic-join", "actor": {"actor_id": "alice", "display_name": "Alice"},
            "kind": "join", "received_at_unix": 0,
        })
        runtime.engine.commit_action("set_day", source="tiktok", context={
            "source_event_id": "historic-comment", "actor_id": "alice", "display_name": "Alice 2",
            "kind": "text", "observed_at_unix": 10,
        })
        paths = [runtime.engine.world_file, runtime.engine.events_file, runtime.engine.deltas_file]
        before = [path.read_bytes() for path in paths]
        runtime.backfill_actor_store()
        actor_bytes = runtime.ACTOR_OBSERVATIONS_FILE.read_bytes()
        runtime.backfill_actor_store()
        self.assertEqual(runtime.ACTOR_OBSERVATIONS_FILE.read_bytes(), actor_bytes)
        self.assertEqual([path.read_bytes() for path in paths], before)
        actor = self.client.get("/api/actors/tiktok/alice").json()
        self.assertEqual(actor["interactions_total"], 2)
        self.assertEqual((actor["first_seen_unix"], actor["last_seen_unix"]), (0, 10))
        self.assertTrue(runtime.engine.verify_replay()["ok"])

    def test_gateway_timestamp_survives_backfill(self):
        response = self.client.post("/api/source/tiktok/event", json={
            "source_event_id": "day-1", "actor_id": "alice", "display_name": "Alice", "text": "dia",
        })
        self.assertEqual(response.status_code, 200)
        actor = self.client.get("/api/actors/tiktok/alice").json()
        self.runtime.actors = self.runtime.ActorStore(Path(self.tmp.name) / "rebuilt-actors.jsonl")
        self.runtime.backfill_actor_store()
        self.assertEqual(self.client.get("/api/actors/tiktok/alice").json(), actor)
        self.assertTrue(self.client.get("/api/replay/verify").json()["ok"])

    def test_legacy_timestamp_is_explicitly_marked_as_backfill_time(self):
        self.runtime.engine.commit_action("set_day", source="tiktok", context={
            "source_event_id": "legacy-1", "actor_id": "alice",
        })
        self.runtime.backfill_actor_store()
        observation = self.runtime.actors.observations()[0]
        self.assertEqual(observation["metadata"]["timestamp_basis"], "backfill")

    def test_health_preserves_mvp007_fields(self):
        health = self.client.get("/api/health").json()
        self.assertEqual(health["version"], self.runtime.app.version)
        self.assertTrue(health["replay_ok"])
        self.assertFalse(health["cross_platform_auto_merge"])
        self.assertIn("audience_rules", health)
        self.assertEqual(health["audience_proposal_log_records"], 0)


if __name__ == "__main__":
    unittest.main()
