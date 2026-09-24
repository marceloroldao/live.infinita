from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_reordering_need_scheduler import NpcReorderingNeedScheduler
from npc_strategy_compiler import NpcStrategyCompiler


class FakeStore:
    def __init__(self, entities):
        self.entities = {row["id"]: row for row in entities}

    def get_entity(self, entity_id):
        row = self.entities.get(entity_id)
        return dict(row) if row is not None else None


class FakePlanner:
    def __init__(self, store):
        self.store = store
        self.regions = None


class FakeProposalLedger:
    def __init__(self):
        self.rows = {}

    def propose(self, **kwargs):
        proposal_id = f"proposal_{len(self.rows) + 1}"
        row = {"proposal_id": proposal_id, "status": "proposed", **kwargs}
        self.rows[proposal_id] = row
        return dict(row)

    def approve(self, proposal_id, **kwargs):
        row = dict(self.rows[proposal_id])
        row["status"] = "approved"
        self.rows[proposal_id] = row
        return dict(row)


class FakePlanScheduler:
    def __init__(self, store):
        self.planner = FakePlanner(store)
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"plan_id": f"plan_{len(self.calls)}"}


class FakeStrategyExecutor:
    def __init__(self):
        self.calls = []

    def start(self, strategy_plan, **kwargs):
        self.calls.append({"strategy_plan": strategy_plan, **kwargs})
        return {"strategy_execution_id": f"exec_{len(self.calls)}", "status": "running"}


class ReorderingCompositeProvider:
    def candidates(self, **kwargs):
        target = kwargs["target_entity_id"]
        return [{
            "strategy_id": "direct",
            "phases": [{"kind": "move_to_entity", "target_entity_id": target, "estimated_ticks": 1}],
            "predicted_satisfaction": kwargs["predicted_satisfaction"],
            "estimated_hops": 1,
            "estimated_risk": 0.0,
            "wait_ticks": 0,
        }]

    def choose(self, candidates, **kwargs):
        row = dict(candidates[0])
        need = str(kwargs.get("need") or "")
        if need == "curiosity":
            row["goal_sequence"] = {
                "goal_sequence_schema": "npc_goal_sequence_v1",
                "npc_id": kwargs.get("actor_entity_id"),
                "mode": "defer_current",
                "goals": [
                    {"need": "safety", "target_entity_id": "safe_place", "role": "prerequisite"},
                    {"need": "curiosity", "target_entity_id": "interesting_place", "role": "current"},
                ],
                "source_horizon": {"defer_to_need": "safety"},
                "mutates_state": False,
            }
        else:
            row["goal_sequence"] = {
                "goal_sequence_schema": "npc_goal_sequence_v1",
                "npc_id": kwargs.get("actor_entity_id"),
                "mode": "current_only",
                "goals": [{"need": need, "target_entity_id": kwargs.get("target_entity_id"), "role": "current"}],
                "mutates_state": False,
            }
        return row, [dict(row)]


class NpcGoalReorderingSchedulerTest(unittest.TestCase):
    def make_scheduler(self, tmp: Path, include_safe_target: bool = True):
        npc = {
            "id": "npc",
            "type": "human",
            "region_id": "r0",
            "position": {"x": 0, "y": 0},
            "properties": {
                "needs": {"safety": 0.60, "energy": 0.0, "social": 0.0, "curiosity": 0.90},
                "safety_target_entity_id": "safe_place",
                "curiosity_target_entity_id": "interesting_place",
            },
        }
        entities = [
            npc,
            {"id": "interesting_place", "type": "place", "region_id": "r0", "position": {"x": 5, "y": 0}, "properties": {}},
        ]
        if include_safe_target:
            entities.append({"id": "safe_place", "type": "place", "region_id": "r0", "position": {"x": 2, "y": 0}, "properties": {}})
        store = FakeStore(entities)
        proposals = FakeProposalLedger()
        plans = FakePlanScheduler(store)
        executor = FakeStrategyExecutor()
        scheduler = NpcReorderingNeedScheduler(
            tmp / "needs.jsonl",
            proposals,
            plans,
            npc_ids=["npc"],
            threshold=0.70,
            cooldown_ticks=10,
            composite_strategy_provider=ReorderingCompositeProvider(),
            strategy_compiler=NpcStrategyCompiler(),
            strategy_executor=executor,
        )
        return scheduler, proposals, plans, executor

    def test_horizon_can_reorder_to_projected_prerequisite_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans, executor = self.make_scheduler(Path(tmpdir))
            row = scheduler.evaluate_tick(1)[0]

            self.assertEqual(row["original_need"], "curiosity")
            self.assertEqual(row["need"], "safety")
            self.assertTrue(row["horizon_reordered"])
            self.assertEqual(row["selected_target_entity_id"], "safe_place")
            self.assertEqual(row["priority"], 1000)
            self.assertEqual(row["reorder_source_sequence"]["goals"][0]["need"], "safety")
            self.assertEqual(len(proposals.rows), 1)
            proposal = next(iter(proposals.rows.values()))
            self.assertEqual(proposal["payload"]["intent"]["need"], "safety")
            self.assertTrue(proposal["metadata"]["horizon_reordered"])
            self.assertEqual(proposal["metadata"]["original_need"], "curiosity")
            self.assertEqual(len(plans.calls), 0)
            self.assertEqual(len(executor.calls), 1)
            terminal_intent = executor.calls[0]["strategy_plan"]["phases"][-1]["intent"]
            self.assertEqual(terminal_intent["need"], "safety")
            self.assertTrue(terminal_intent["need_outcome_eligible"])

    def test_missing_prerequisite_target_fails_closed_to_current_need(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans, executor = self.make_scheduler(Path(tmpdir), include_safe_target=False)
            row = scheduler.evaluate_tick(1)[0]

            self.assertEqual(row["original_need"], "curiosity")
            self.assertEqual(row["need"], "curiosity")
            self.assertFalse(row["horizon_reordered"])
            self.assertEqual(row["selected_target_entity_id"], "interesting_place")
            self.assertEqual(len(proposals.rows), 1)
            proposal = next(iter(proposals.rows.values()))
            self.assertEqual(proposal["payload"]["intent"]["need"], "curiosity")
            self.assertEqual(len(executor.calls), 1)


if __name__ == "__main__":
    unittest.main()
