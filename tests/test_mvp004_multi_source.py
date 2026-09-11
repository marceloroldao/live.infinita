from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATEWAY_DIR = ROOT / "apps" / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from adapters import adapt_source  # noqa: E402
from pipeline import GatewayPipeline  # noqa: E402


class MVP004MultiSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.pipeline = GatewayPipeline()

    def test_all_sources_share_same_envelope_contract(self) -> None:
        for source in ["simulator", "api", "tiktok", "youtube", "agent"]:
            with self.subTest(source=source):
                env = adapt_source(source, {
                    "source_event_id": f"{source}-001",
                    "actor_id": "actor-1",
                    "display_name": "Tester",
                    "text": "noite",
                    "metadata": {"sample": True},
                })
                self.assertEqual(env.envelope_version, "1.0")
                self.assertEqual(env.source, source)
                self.assertEqual(env.source_event_id, f"{source}-001")
                self.assertEqual(env.actor.actor_id, "actor-1")
                self.assertEqual(env.text, "noite")

    def test_same_text_yields_same_action_for_all_sources(self) -> None:
        actions = set()
        for source in ["simulator", "api", "tiktok", "youtube", "agent"]:
            event, proposed, validation = self.pipeline.process({
                "source": source,
                "source_event_id": f"{source}-night",
                "actor_id": "actor-1",
                "text": "noite",
                "metadata": {},
            })
            self.assertEqual(event.source, source)
            self.assertTrue(validation.accepted)
            actions.add(proposed.action)
        self.assertEqual(actions, {"set_night"})

    def test_unknown_adapter_is_rejected_before_runtime(self) -> None:
        with self.assertRaises(ValueError):
            self.pipeline.process({
                "source": "unknown-network",
                "source_event_id": "x-1",
                "actor_id": "actor-1",
                "text": "noite",
            })


if __name__ == "__main__":
    unittest.main()
