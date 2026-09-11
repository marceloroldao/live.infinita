from pathlib import Path
import importlib.util
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "apps" / "gateway"
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(RUNTIME_DIR))

from pipeline import GatewayPipeline
from engine import DeterministicWorldEngine


class MVP003PipelineTest(unittest.TestCase):
    def test_normalized_event_to_validated_runtime_commit(self):
        pipeline = GatewayPipeline()
        normalized, proposed, validation = pipeline.process({
            "source": "simulator",
            "actor_id": "tester",
            "kind": "text",
            "text": "noite",
            "metadata": {"test": True},
        })
        self.assertEqual(normalized.source, "simulator")
        self.assertEqual(proposed.action, "set_night")
        self.assertTrue(validation.accepted)

        with tempfile.TemporaryDirectory() as tmp:
            engine = DeterministicWorldEngine(
                ROOT / "examples" / "world-state.mvp001.bootstrap.json",
                Path(tmp),
            )
            event, delta, world = engine.commit_action(
                validation.action,
                source=normalized.source,
                context={"actor_id": normalized.actor.actor_id, "text": normalized.text},
            )
            self.assertEqual(event["source"], "simulator")
            self.assertEqual(event["type"], "validated_action")
            self.assertEqual(world["environment"]["period"], "night")
            self.assertEqual(delta["result_hash"], world["state_hash"])
            self.assertTrue(engine.verify_replay()["ok"])

    def test_unknown_intent_is_rejected(self):
        pipeline = GatewayPipeline()
        _, proposed, validation = pipeline.process({
            "source": "simulator",
            "actor_id": "tester",
            "kind": "text",
            "text": "faça qualquer coisa",
        })
        self.assertEqual(proposed.action, "unknown")
        self.assertFalse(validation.accepted)


if __name__ == "__main__":
    unittest.main()
