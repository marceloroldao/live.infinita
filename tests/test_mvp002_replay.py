from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = ROOT / "apps" / "world-runtime" / "engine.py"
BOOTSTRAP = ROOT / "examples" / "world-state.mvp001.bootstrap.json"

spec = importlib.util.spec_from_file_location("live_infinita_engine", ENGINE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(module)
DeterministicWorldEngine = module.DeterministicWorldEngine


class DeterministicReplayTest(unittest.TestCase):
    def test_replay_matches_committed_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DeterministicWorldEngine(BOOTSTRAP, Path(temp_dir))
            actions = [
                "spawn_person",
                "move_tree",
                "set_night",
                "toggle_fire",
                "move_tree",
                "set_day",
            ]
            for action in actions:
                engine.commit_action(action)

            verification = engine.verify_replay()
            self.assertTrue(verification["ok"])
            self.assertEqual(verification["events"], len(actions))
            self.assertEqual(verification["deltas"], len(actions))
            self.assertEqual(verification["current_hash"], verification["replay_hash"])

    def test_same_actions_produce_same_final_hash(self) -> None:
        actions = ["spawn_person", "set_night", "toggle_fire", "move_tree"]
        hashes = []
        for _ in range(2):
            with tempfile.TemporaryDirectory() as temp_dir:
                engine = DeterministicWorldEngine(BOOTSTRAP, Path(temp_dir))
                for action in actions:
                    engine.commit_action(action)
                hashes.append(engine.load_world()["state_hash"])
        self.assertEqual(hashes[0], hashes[1])


if __name__ == "__main__":
    unittest.main()
