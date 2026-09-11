import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_DIR = ROOT / "apps" / "ai"
if str(AI_DIR) not in sys.path:
    sys.path.insert(0, str(AI_DIR))

from router import AIRouter, AIRouterError  # noqa: E402


class AIRouterTest(unittest.TestCase):
    def test_allowed_action_is_normalized(self):
        router = AIRouter(
            api_key="test",
            model="gpt-test",
            transport=lambda payload: {
                "output_text": '{"action":"set_night","confidence":0.91,"reason":"pedido explícito"}'
            },
        )
        proposal = router.propose("deixe a clareira escura")
        self.assertEqual(proposal.action, "set_night")
        self.assertTrue(proposal.actionable)
        self.assertEqual(proposal.to_dict()["gateway_text"], "noite")

    def test_unknown_action_becomes_non_actionable(self):
        router = AIRouter(
            api_key="test",
            model="gpt-test",
            transport=lambda payload: {
                "output_text": '{"action":"delete_world","confidence":1,"reason":"não permitido"}'
            },
        )
        proposal = router.propose("apague tudo")
        self.assertIsNone(proposal.action)
        self.assertFalse(proposal.actionable)

    def test_none_remains_non_actionable(self):
        router = AIRouter(
            api_key="test",
            model="gpt-test",
            transport=lambda payload: {
                "output_text": '{"action":"none","confidence":0.2,"reason":"ambíguo"}'
            },
        )
        proposal = router.propose("faça algo legal")
        self.assertIsNone(proposal.action)
        self.assertFalse(proposal.actionable)

    def test_confidence_is_clamped(self):
        router = AIRouter(
            api_key="test",
            model="gpt-test",
            transport=lambda payload: {
                "output_text": '{"action":"set_day","confidence":7,"reason":"teste"}'
            },
        )
        proposal = router.propose("clareie")
        self.assertEqual(proposal.confidence, 1.0)

    def test_invalid_json_is_rejected(self):
        router = AIRouter(
            api_key="test",
            model="gpt-test",
            transport=lambda payload: {"output_text": "não-json"},
        )
        with self.assertRaises(AIRouterError):
            router.propose("noite")

    def test_empty_text_is_rejected(self):
        router = AIRouter(api_key="test", model="gpt-test", transport=lambda payload: {})
        with self.assertRaises(AIRouterError):
            router.propose("   ")


if __name__ == "__main__":
    unittest.main()
