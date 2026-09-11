from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
ACTORS_DIR = ROOT / "apps" / "actors"
if str(ACTORS_DIR) not in sys.path:
    sys.path.insert(0, str(ACTORS_DIR))

from store import ActorStore


class ActorStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ActorStore(Path(self.tmp.name) / "actor-observations.jsonl")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_same_actor_folds_multiple_observations(self) -> None:
        self.store.observe(source="tiktok", actor_id="alice", display_name="Alice", kind="join", source_event_id="1")
        self.store.observe(source="tiktok", actor_id="alice", display_name="Alice 2", kind="like", source_event_id="2")
        actors = self.store.actors()
        self.assertEqual(len(actors), 1)
        actor = actors[0]
        self.assertEqual(actor["actor_key"], "tiktok:alice")
        self.assertEqual(actor["interactions_total"], 2)
        self.assertEqual(actor["interactions_by_kind"], {"join": 1, "like": 1})
        self.assertEqual(actor["display_name"], "Alice 2")
        self.assertEqual(actor["display_names_seen"], ["Alice", "Alice 2"])

    def test_cross_platform_ids_are_not_merged(self) -> None:
        self.store.observe(source="tiktok", actor_id="alice", display_name="Alice", kind="join", source_event_id="tt-1")
        self.store.observe(source="youtube", actor_id="alice", display_name="Alice", kind="join", source_event_id="yt-1")
        keys = {actor["actor_key"] for actor in self.store.actors()}
        self.assertEqual(keys, {"tiktok:alice", "youtube:alice"})

    def test_source_event_is_idempotent(self) -> None:
        first = self.store.observe(source="tiktok", actor_id="alice", display_name="Alice", kind="join", source_event_id="same")
        second = self.store.observe(source="tiktok", actor_id="alice", display_name="Alice", kind="join", source_event_id="same")
        self.assertTrue(first)
        self.assertFalse(second)
        self.assertEqual(len(self.store.observations()), 1)


if __name__ == "__main__":
    unittest.main()
