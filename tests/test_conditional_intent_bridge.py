from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

bridge_module = load("conditional_intent_bridge_test_module", RUNTIME / "conditional_intent_bridge.py")
ConditionalIntentBridge = bridge_module.ConditionalIntentBridge


class FakeConditionScheduler:
    def __init__(self):
        self.row = {"conditional_event_id": "cev_1", "fire_count": 0}
        self.bump = False

    def current(self):
        return [dict(self.row)]

    def evaluate_tick(self, tick):
        if self.bump:
            self.row["fire_count"] += 1
            self.bump = False
        return [dict(self.row)]


class FakePlanScheduler:
    def __init__(self):
        self.by_key = {}
        self.calls = []

    def schedule(self, *, intent, principal, proposer_id, proposal_id=None, idempotency_key=None):
        if idempotency_key in self.by_key:
            return self.by_key[idempotency_key]
        row = {"plan_id": f"plan_{len(self.by_key)+1}", "status": "planned", "idempotency_key": idempotency_key}
        self.by_key[idempotency_key] = row
        self.calls.append({"intent": intent, "principal": principal, "proposer_id": proposer_id, "proposal_id": proposal_id, "idempotency_key": idempotency_key})
        return row


class ConditionalIntentBridgeTest(unittest.TestCase):
    def test_new_fire_creates_one_plan_and_same_fire_does_not_duplicate(self):
        conditions = FakeConditionScheduler()
        plans = FakePlanScheduler()
        bridge = ConditionalIntentBridge(conditions, plans)
        binding = {
            "cev_1": {
                "intent": {"intent": "move_to_entity", "actor_entity_id": "npc", "target_entity_id": "nov"},
                "principal": {"source": "world", "actor_id": "npc", "authority": "entity_agent", "subject_entity_id": "npc"},
                "proposer_id": "conditional-world",
            }
        }
        self.assertEqual(bridge.evaluate_and_schedule(1, binding), [])
        conditions.bump = True
        first = bridge.evaluate_and_schedule(2, binding)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0]["plan_id"], "plan_1")
        self.assertEqual(bridge.evaluate_and_schedule(2, binding), [])
        self.assertEqual(len(plans.calls), 1)

    def test_second_real_fire_creates_second_plan(self):
        conditions = FakeConditionScheduler()
        plans = FakePlanScheduler()
        bridge = ConditionalIntentBridge(conditions, plans)
        binding = {
            "cev_1": {
                "intent": {"intent": "move_to_position", "actor_entity_id": "npc", "position": {"x": 1, "y": 2}, "region_id": "village"},
                "principal": {"source": "world", "actor_id": "npc", "authority": "entity_agent", "subject_entity_id": "npc"},
                "proposer_id": "conditional-world",
            }
        }
        conditions.bump = True
        bridge.evaluate_and_schedule(1, binding)
        conditions.bump = True
        second = bridge.evaluate_and_schedule(3, binding)
        self.assertEqual(second[0]["plan_id"], "plan_2")
        self.assertEqual(len(plans.calls), 2)


if __name__ == "__main__":
    unittest.main()
