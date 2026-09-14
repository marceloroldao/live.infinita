from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
WORLD_RUNTIME = ROOT / "apps" / "world-runtime"
AI_DIR = ROOT / "apps" / "ai"
GATEWAY_DIR = ROOT / "apps" / "gateway"
for path in (ROOT, WORLD_RUNTIME, AI_DIR, GATEWAY_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from npc_idle_wander import NpcIdleWander  # noqa: E402
from router import AIRouter  # noqa: E402
from pipeline import GatewayPipeline  # noqa: E402


class _FakeStore:
    def __init__(self) -> None:
        self.entities = {
            "nov": {"id": "nov", "region_id": "clearing", "position": {"x": 640, "y": 360}},
        }

    def get_entity(self, entity_id: str):
        return self.entities.get(entity_id)


class _FakeRegions:
    def __init__(self) -> None:
        self.rows = {
            "clearing": SimpleNamespace(id="clearing", center=(640.0, 360.0), radius=150.0, neighbors=("shelter",)),
            "shelter": SimpleNamespace(id="shelter", center=(930.0, 390.0), radius=120.0, neighbors=("clearing",)),
        }

    def get(self, region_id: str):
        return self.rows.get(region_id)


class _FakeLedger:
    TERMINAL = frozenset({"completed", "failed", "cancelled"})

    def __init__(self) -> None:
        self.rows = []

    def active(self):
        return [row for row in self.rows if row.get("status") not in self.TERMINAL]


class _FakeScheduler:
    def __init__(self) -> None:
        self.planner = SimpleNamespace(store=_FakeStore(), regions=_FakeRegions())
        self.ledger = _FakeLedger()
        self.scheduled = []

    def schedule(self, **kwargs):
        row = {
            "plan_id": f"plan-{len(self.scheduled) + 1}",
            "actor_entity_id": kwargs["intent"].get("actor_entity_id"),
            "status": "planned",
            **kwargs,
        }
        self.scheduled.append(row)
        self.ledger.rows.append(row)
        return row


class LiveAutonomyAudienceAITests(unittest.TestCase):
    def test_idle_wander_schedules_low_priority_movement(self) -> None:
        scheduler = _FakeScheduler()
        wander = NpcIdleWander(scheduler, npc_ids=["nov"], interval_ticks=8, priority=25)
        rows = wander.evaluate_tick(8)
        self.assertEqual(rows[0]["status"], "scheduled")
        self.assertEqual(scheduler.scheduled[0]["intent"]["intent"], "move_to_position")
        self.assertEqual(scheduler.scheduled[0]["principal"]["authority"], "entity_agent")
        self.assertEqual(scheduler.scheduled[0]["priority"], 25)

    def test_idle_wander_yields_to_active_need(self) -> None:
        scheduler = _FakeScheduler()
        wander = NpcIdleWander(scheduler, npc_ids=["nov"], interval_ticks=8, priority=25)
        rows = wander.evaluate_tick(8, blocked_npc_ids={"nov"})
        self.assertEqual(rows[0]["status"], "need_active")
        self.assertEqual(scheduler.scheduled, [])

    def test_ai_router_maps_natural_walk_request_to_closed_action(self) -> None:
        router = AIRouter(
            api_key="test",
            model="test-model",
            transport=lambda _payload: {
                "output_text": json.dumps({
                    "action": "nov_to_fire",
                    "confidence": 0.96,
                    "reason": "pedido para Nov caminhar até a fogueira",
                })
            },
        )
        proposal = router.propose("Nov vai para perto da fogueira")
        self.assertTrue(proposal.actionable)
        self.assertEqual(proposal.action, "nov_to_fire")
        self.assertEqual(proposal.to_dict()["gateway_text"], "nov fogueira")

    def test_gateway_accepts_deterministic_nov_commands(self) -> None:
        pipeline = GatewayPipeline()
        _event, proposed, validation = pipeline.process({
            "source": "tiktok",
            "source_event_id": "comment-1",
            "actor_id": "viewer-1",
            "display_name": "Viewer",
            "kind": "text",
            "text": "nov explorar",
            "metadata": {},
        })
        self.assertEqual(proposed.action, "nov_explore")
        self.assertTrue(validation.accepted)

    def test_audience_auto_allowlist_excludes_world_control(self) -> None:
        source = (WORLD_RUNTIME / "main_spatial.py").read_text(encoding="utf-8")
        auto_block = source.split("_AUDIENCE_AUTO_ACTIONS = frozenset({", 1)[1].split("})", 1)[0]
        self.assertIn('"nov_explore"', auto_block)
        self.assertIn('"toggle_fire"', auto_block)
        self.assertNotIn('"set_night"', auto_block)
        self.assertNotIn('"reset"', auto_block)
        self.assertIn('metadata.get("ai_auto_approved")', source)
        self.assertIn('authority = "world_agent"', source)


if __name__ == "__main__":
    unittest.main()
