from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "apps" / "gateway"
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(RUNTIME_DIR))

from engine import DeterministicWorldEngine  # noqa: E402
from pipeline import GatewayPipeline  # noqa: E402

AGG_MODULE = ROOT / "apps" / "audience" / "aggregator.py"
spec = importlib.util.spec_from_file_location("soak_audience_aggregator", AGG_MODULE)
agg_module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = agg_module
spec.loader.exec_module(agg_module)
AudienceAggregator = agg_module.AudienceAggregator


class LiveSoakTest(unittest.TestCase):
    def test_long_session_remains_bounded_and_replayable(self):
        pipeline = GatewayPipeline()
        audience = AudienceAggregator()

        # Simulate a high-volume 20-minute audience stream at deterministic timestamps.
        proposals = 0
        for i in range(20_000):
            kind = "like" if i % 5 else "join"
            proposals += len(audience.ingest({"kind": kind}, now=10_000 + i * 0.06))

        self.assertGreater(proposals, 0)
        # Retention is window-based, not session-length based.
        self.assertLess(audience.retained_event_count(), 1000)

        with tempfile.TemporaryDirectory() as tmp:
            engine = DeterministicWorldEngine(
                ROOT / "examples" / "world-state.mvp001.bootstrap.json",
                Path(tmp),
            )

            accepted = 0
            last_world = None
            commands = ("noite", "dia", "fogueira")
            for i in range(500):
                normalized, _proposed, validation = pipeline.process({
                    "source": "simulator",
                    "actor_id": f"soak-{i % 25}",
                    "kind": "text",
                    "text": commands[i % len(commands)],
                    "metadata": {"soak": True, "sequence": i},
                })
                if not validation.accepted:
                    continue
                _event, _delta, last_world = engine.commit_action(
                    validation.action,
                    source=normalized.source,
                    context={
                        "actor_id": normalized.actor.actor_id,
                        "text": normalized.text,
                        "soak_sequence": i,
                    },
                )
                accepted += 1

            self.assertEqual(accepted, 500)
            self.assertIsNotNone(last_world)
            assert last_world is not None
            self.assertGreaterEqual(last_world["sequence"], 500)
            verification = engine.verify_replay()
            self.assertTrue(verification["ok"], verification)
            self.assertEqual(verification["current_hash"], verification["replay_hash"])
            self.assertEqual(verification["current_hash"], last_world["state_hash"])
            self.assertEqual(verification["events"], 500)
            self.assertEqual(verification["deltas"], 500)


if __name__ == "__main__":
    unittest.main()
