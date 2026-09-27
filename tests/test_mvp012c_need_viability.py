from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for item in (str(ROOT), str(RUNTIME)):
    if item not in sys.path:
        sys.path.insert(0, item)

from cognitive_contextual import (  # noqa: E402
    evaluate_contextual_forecast,
    freeze_contextual_forecast,
    stationary_evidence,
)
from npc_audited_reordering_need_scheduler import NpcAuditedReorderingNeedScheduler  # noqa: E402
from tests.test_npc_need_scheduler import FakeStore, FakePlanScheduler, FakeProposalLedger  # noqa: E402


class DynamicNeeds:
    def __init__(self, values):
        self.values = dict(values)

    def get_needs(self, _npc):
        return deepcopy(self.values)


class NeedFallbackTests(unittest.TestCase):
    def build(self, path, *, social_target=False, curiosity_target=True):
        props = {
            "needs": {"social": 0.1, "curiosity": 0.2},
            "curiosity_target_entity_id": "ancient_tree" if curiosity_target else "",
        }
        if social_target:
            props["social_target_entity_id"] = "visitor"
        entities = [{"id": "nov", "type": "human", "region_id": "clearing",
                     "position": {"x": 0, "y": 0}, "properties": props}]
        if curiosity_target:
            entities.append({"id": "ancient_tree", "type": "tree", "region_id": "forest",
                             "position": {"x": 50, "y": 0}, "properties": {}})
        if social_target:
            entities.append({"id": "visitor", "type": "human", "region_id": "clearing",
                             "position": {"x": 10, "y": 0}, "properties": {}})
        store = FakeStore(entities)
        proposals = FakeProposalLedger()
        plans = FakePlanScheduler(store)
        needs = DynamicNeeds({"social": 1.0, "curiosity": 1.0, "safety": 0.0, "energy": 0.0})
        scheduler = NpcAuditedReorderingNeedScheduler(
            path, proposals, plans, npc_ids=["nov"], cooldown_ticks=10,
            threshold=0.7, need_state_provider=needs,
        )
        return scheduler, store, needs, proposals, plans

    def test_social_missing_curiosity_viable_still_schedules_one_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler, store, needs, proposals, plans = self.build(Path(directory) / "needs.jsonl")
            rows = scheduler.evaluate_tick(10)
            self.assertEqual([(r["need"], r["status"]) for r in rows],
                             [("social", "no_target"), ("curiosity", "scheduled")])
            self.assertEqual(rows[1]["highest_urgent_need"], "social")
            self.assertEqual(rows[1]["original_need"], "curiosity")
            self.assertFalse(rows[1]["horizon_reordered"])
            self.assertEqual(rows[1]["selected_target_entity_id"], "ancient_tree")
            self.assertEqual(rows[1]["skipped_unresolved_needs"], [
                {"need": "social", "rank": 0, "reason": "no_viable_target",
                 "target_references": []},
            ])
            self.assertEqual(len(plans.calls), 1)
            self.assertEqual(len(proposals.rows), 1)
            payload = next(iter(proposals.rows.values()))
            self.assertEqual(payload["metadata"]["skipped_unresolved_needs"],
                             rows[1]["skipped_unresolved_needs"])
            self.assertEqual([r["status"] for r in scheduler.history()], ["no_target", "scheduled"])
            self.assertEqual(rows[1]["viability_selection_schema"], "npc_need_viability_v1")

    def test_all_unresolved_audited_coalesced_and_recovery_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "needs.jsonl"
            scheduler, store, needs, proposals, plans = self.build(path, curiosity_target=False)
            self.assertEqual([r["status"] for r in scheduler.evaluate_tick(1)],
                             ["no_target", "no_target"])
            self.assertEqual(len(scheduler.history()), 2)
            again = NpcAuditedReorderingNeedScheduler(
                path, proposals, plans, npc_ids=["nov"], threshold=0.7,
                cooldown_ticks=10, need_state_provider=needs,
            )
            self.assertEqual([r["status"] for r in again.evaluate_tick(2)],
                             ["no_target", "no_target"])
            self.assertEqual(len(again.history()), 2)
            store.entities["nov"]["properties"]["curiosity_target_entity_id"] = "ancient_tree"
            store.entities["ancient_tree"] = {
                "id": "ancient_tree", "region_id": "forest", "position": {"x": 50, "y": 0},
            }
            changed = again.evaluate_tick(3)
            self.assertEqual([r["status"] for r in changed], ["no_target", "scheduled"])
            self.assertEqual(again.history()[-1]["resolved_no_target_since_tick"], 1)
            self.assertEqual(len(plans.calls), 1)

    def test_valid_higher_priority_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler, store, needs, proposals, plans = self.build(
                Path(directory) / "needs.jsonl", social_target=True)
            rows = scheduler.evaluate_tick(1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["need"], "social")
            self.assertEqual(rows[0]["selected_target_entity_id"], "visitor")
            self.assertEqual(rows[0]["skipped_unresolved_needs"], [])
            self.assertEqual(len(plans.calls), 1)

    def test_lower_need_cooldown_and_active_goal_remain_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler, store, needs, proposals, plans = self.build(Path(directory) / "needs.jsonl")
            needs.values["social"] = 0.1
            first = scheduler.evaluate_tick(1)[0]
            self.assertEqual(first["need"], "curiosity")
            needs.values["social"] = 1.0
            second = scheduler.evaluate_tick(3)
            self.assertEqual([(r["need"], r["status"]) for r in second],
                             [("social", "no_target"), ("curiosity", "cooldown")])
            self.assertEqual(len(plans.calls), 1)
            class Ledger:
                def active(self):
                    return [{"actor_entity_id": "nov", "intent": {"need": "curiosity"},
                             "status": "waiting", "plan_id": first["plan_id"]}]
            plans.ledger = Ledger()
            third = scheduler.evaluate_tick(11)
            self.assertEqual([r["status"] for r in third],
                             ["no_target", "already_active"])
            self.assertEqual(len(plans.calls), 1)

    def test_contextual_target_is_read_once_before_tick(self):
        with tempfile.TemporaryDirectory() as directory:
            _, store, needs, _, _ = self.build(Path(directory) / "needs.jsonl")
            calls = []
            def provider(key):
                calls.append(key)
                return store.get_entity(key)
            forecast, _ = freeze_contextual_forecast(
                frame_id="f", world_version=1, world_sequence=2,
                observer=store.get_entity("nov"), needs=needs.get_needs("nov"),
                target_provider=provider,
            )
            self.assertEqual(forecast["status"], "issued")
            self.assertEqual(calls, ["ancient_tree"])

    def test_contextual_observer_skips_only_unresolvable_target(self):
        with tempfile.TemporaryDirectory() as directory:
            scheduler, store, needs, _, _ = self.build(Path(directory) / "needs.jsonl")
            observer = store.get_entity("nov")
            f, target = freeze_contextual_forecast(
                frame_id="before", world_version=12, world_sequence=20,
                observer=observer, needs=needs.get_needs("nov"),
                target_provider=store.get_entity, need_source="npc_need_dynamics",
                environment={"period": "day", "weather": "clear"},
            )
            self.assertEqual(f["status"], "issued")
            self.assertEqual(f["highest_urgent_need"], "social")
            self.assertEqual(f["selected_need"], "curiosity")
            self.assertEqual(f["target_entity_id"], "ancient_tree")
            self.assertEqual(f["skipped_unresolved_needs"][0]["need"], "social")
            self.assertFalse(f["predicts_action"])
            self.assertEqual(evaluate_contextual_forecast(
                f, before=observer, after={**observer, "position": {"x": 10, "y": 0}},
                target_after=target,
            )["status"], "hit")
            status = stationary_evidence(
                movement_distance=0,
                tick_result={"npc_needs": [{"npc_id": "nov", "status": "no_target"},
                                            {"npc_id": "nov", "status": "scheduled"}], "plans": []},
                contextual_forecast=f,
            )
            self.assertEqual(status["evidence_label"], "need_scheduled_without_displacement")
            self.assertFalse(status["causal_explanation_evaluable"])


if __name__ == "__main__":
    unittest.main()
