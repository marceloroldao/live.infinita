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
from npc_audited_reordering_need_scheduler import NpcAuditedReorderingNeedScheduler
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
        self.rows = []

    def start(self, strategy_plan, **kwargs):
        self.calls.append({"strategy_plan": strategy_plan, **kwargs})
        row = {
            "strategy_execution_id": f"exec_{len(self.calls)}", "status": "running",
            "strategy_plan": strategy_plan, "child_plan_id": None,
        }
        self.rows.append(row)
        return dict(row)

    def current(self):
        return [dict(row) for row in self.rows]


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
    def make_scheduler(self, tmp: Path, include_safe_target: bool = True, scheduler_type=NpcReorderingNeedScheduler):
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
        scheduler = scheduler_type(
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

    def test_production_audited_scheduler_reuses_original_active_need(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans, executor = self.make_scheduler(
                Path(tmpdir), scheduler_type=NpcAuditedReorderingNeedScheduler
            )
            npc = plans.planner.store.entities["npc"]
            npc["properties"]["needs"] = {"safety": 0.95, "curiosity": 0.0}
            first = scheduler.evaluate_tick(1)[0]
            self.assertEqual(first["need"], "safety")
            second = scheduler.evaluate_tick(11)[0]
            self.assertEqual(second["status"], "already_active")
            self.assertEqual(second["strategy_execution_id"], first["strategy_execution_id"])
            self.assertEqual(len(executor.calls), 1)
            self.assertEqual(len(proposals.rows), 1)
            self.assertEqual(len(scheduler.history()), 1)
            executor.rows[0]["status"] = "completed"
            third = scheduler.evaluate_tick(11)[0]
            self.assertEqual(third["status"], "scheduled")
            self.assertEqual(len(executor.calls), 2)

    def test_production_audited_scheduler_reuses_projected_prerequisite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, proposals, plans, executor = self.make_scheduler(
                Path(tmpdir), scheduler_type=NpcAuditedReorderingNeedScheduler
            )
            first = scheduler.evaluate_tick(1)[0]
            self.assertEqual(first["original_need"], "curiosity")
            self.assertEqual(first["need"], "safety")
            second = scheduler.evaluate_tick(11)[0]
            self.assertEqual(second["status"], "already_active")
            self.assertTrue(second["horizon_reordered"])
            self.assertEqual(second["strategy_execution_id"], first["strategy_execution_id"])
            self.assertEqual(len(executor.calls), 1)
            self.assertEqual(len(proposals.rows), 1)
            self.assertEqual(len(scheduler.history()), 1)


    def test_audited_reconsideration_uses_latest_scheduled_index(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler, _, _, _ = self.make_scheduler(
                Path(tmpdir), scheduler_type=NpcAuditedReorderingNeedScheduler,
            )
            with patch.object(scheduler, "_iter_history", wraps=scheduler._iter_history) as replay:
                initial = scheduler.evaluate_tick(1)[0]
                self.assertEqual(replay.call_count, 1)
                self.assertEqual(initial["need"], "safety")
                self.assertEqual(
                    scheduler._pending_reorder_for("npc", "curiosity")["proposal_id"],
                    initial["proposal_id"],
                )
                self.assertEqual(scheduler._pending_reorder_for("npc", "curiosity")["tick"], 1)
                self.assertEqual(replay.call_count, 1)
                followup = scheduler._append({
                    "npc_id": "npc", "need": "curiosity", "original_need": "curiosity",
                    "status": "scheduled", "tick": 15,
                })
                self.assertEqual(
                    followup["reconsidered_from_proposal_id"], initial["proposal_id"]
                )
                self.assertIsNone(scheduler._pending_reorder_for("npc", "curiosity"))
                self.assertEqual(scheduler._last_tick("npc", "curiosity"), 15)
                self.assertEqual(replay.call_count, 1)


if __name__ == "__main__":
    unittest.main()
