"""MVP-018L: immutable current-frame sampler from cold-backed World State."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_current_frame import sample_current_nov_frame, RecallBlocked


class CurrentNovFrameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.world_path = root / "world.json"
        self.lock = root / "world-mutation.lock"
        self.lock.touch()
        self.cold = root / "cold-store"
        self.regions = self.cold / "regions"
        self.regions.mkdir(parents=True)
        self.nov = {
            "id": "nov", "type": "human", "region_id": "shelter",
            "position": {"x": 1, "y": 2},
            "properties": {"needs": {"curiosity": 0.7}},
        }
        self.world = {
            "world_id": "test-live", "current_tick": 101,
            "version": 20, "sequence": 100,
            "state_hash": "a" * 64,
            "environment": {"period": "night", "weather": "rain"},
            "entities": [], "cold_entities": {"mode": "region_file_store"},
        }
        self.write_world()
        self.write_region()
        self.write_manifest()

    def write_world(self):
        self.world_path.write_text(json.dumps(self.world))

    def write_region(self):
        self.region_path = self.regions / (
            sha256(self.nov["region_id"].encode()).hexdigest() + ".json"
        )
        self.region_path.write_text(json.dumps([self.nov]))

    def write_manifest(self):
        (self.cold / "manifest.json").write_text(json.dumps({
            "version": 1, "entity_region": {"nov": self.nov["region_id"]},
            "region_counts": {self.nov["region_id"]: 1},
        }))

    def sample(self):
        return sample_current_nov_frame(
            world_path=self.world_path, cold_root=self.cold,
            mutation_lock=self.lock,
        )

    def test_observes_current_region_and_environment_without_writes(self):
        original = {p: p.read_bytes() for p in (
            self.world_path, self.lock, self.region_path, self.cold / "manifest.json",
        )}
        frame = self.sample()
        self.assertEqual(frame.tick_id, 101)
        self.assertIn("live:region:shelter", frame.state_addresses)
        self.assertIn("live:period:night", frame.state_addresses)
        self.assertIn("live:weather:rain", frame.state_addresses)
        self.assertIn("live:need:curiosity:high", frame.state_addresses)
        self.assertEqual(frame.provenance["authority"], "read-only-cognitive-projection")
        self.assertEqual(frame.candidate_outcomes, ())
        self.assertEqual(original, {path: path.read_bytes() for path in original})

    def test_observes_change_of_region_and_tick_not_old_episode(self):
        self.nov["region_id"] = "deep_forest"
        self.world["current_tick"] = 110
        self.world["environment"]["weather"] = "sun"
        self.write_world()
        self.write_region()
        self.write_manifest()
        frame = self.sample()
        self.assertIn("live:region:deep_forest", frame.state_addresses)
        self.assertNotIn("live:region:shelter", frame.state_addresses)
        self.assertIn("live:weather:sun", frame.state_addresses)
        self.assertEqual(frame.tick_id, 110)

    def test_rejects_manifest_entity_disagreement(self):
        # Corrupt the original manifest-addressed region, not a new region:
        # otherwise the unchanged old row would still be valid.
        self.nov["region_id"] = "deep_forest"
        self.region_path.write_text(json.dumps([self.nov]))
        with self.assertRaises(RecallBlocked):
            self.sample()

    def test_rejects_missing_entity_or_non_cold_world(self):
        self.region_path.write_text(json.dumps([]))
        with self.assertRaises(RecallBlocked):
            self.sample()
        self.write_region()
        self.world["cold_entities"] = {"mode": "not-cold"}
        self.write_world()
        with self.assertRaises(RecallBlocked):
            self.sample()

    def test_rejects_symlink_and_oversized_region(self):
        self.region_path.unlink()
        self.region_path.symlink_to(self.world_path)
        with self.assertRaises(RecallBlocked):
            self.sample()
        self.region_path.unlink()
        self.region_path.write_bytes(b"[" + b" " * (256 * 1024 + 1) + b"]")
        with self.assertRaises(RecallBlocked):
            self.sample()

    def test_shared_nonblocking_lock_abstains_on_writer(self):
        # flock locks are owned by file descriptions; a second independent fd
        # must be rejected while the writer's exclusive lock is held.
        import fcntl
        with self.lock.open("rb") as holder:
            fcntl.flock(holder.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                with self.assertRaisesRegex(RecallBlocked, "commit_busy"):
                    self.sample()
            finally:
                fcntl.flock(holder.fileno(), fcntl.LOCK_UN)


if __name__ == "__main__":
    unittest.main()
