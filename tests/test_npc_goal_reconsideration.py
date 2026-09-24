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


class FakeNeedState:
    def __init__(self, values):
        self.values = dict(values)

    def get_needs(self, npc_id):
        return dict(self.values)


class FakePlanner:
    def __init__(self, store):
        self.store = store
        self.regions = None


class FakePlanScheduler:
    def __init__(self, store):
        self.planner = FakePlanner(store)
        self.calls = []

    def schedule(self, **kwargs):
        self.calls.append(kwargs)
        return {"plan_id": f"plan_{len(self.calls)}", "status": "planned"}


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


class TwoPassComposite:
    def __init__(self):
        self.curiosity_calls = 0

    def candidates(self, **kwargs):
        return [{
            "strategy_id": "direct",
            "phases": [{"kind": "move_to_entity", "target_entity_id": kwargs["target_entity_id"]}],
            "predicted_satisfaction": kwargs["predicted_satisfaction"],
            "estimated_hops": 1,
            "estimated_risk": 0.0,
            "wait_ticks": 0,
        }]

    def choose(self, candidates, **kwargs):
        row = dict(candidates[0])
        need = kwargs.get("need")
        if need == "curiosity":
            self.curiosity_calls += 1
            if self.curiosity_calls == 1:
                row["goal_sequence"] = {
                    "goal_sequence_schema": "npc_goal_sequence_v1",
                    "mode": "defer_current",
                    "goals": [
                        {"need": "safety", "target_entity_id": "shelter", "role": "prerequisite"},
                        {"need": "curiosity", "target_entity_id": "tree", "role": "current"},
                    ],
                    "mutates_state": False,
                }
        return row, [dict(row)]


class FakeExecutor:
    def __init__(self):
        self.calls = []

    def start(self, plan, **kwargs):
        self.calls.append({"plan": plan, **kwargs})
        return {"strategy_execution_id": f"exec_{len(self.calls)}", "status": "running"}


class NpcGoalReconsiderationTest(unittest.TestCase):
    def test_original_goal_is_reconsidered_from_new_state_not_auto_resumed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            npc = {
                "id": "nov",
                "type": "human",
                "region_id": "r0",
                "position": {"x": 0, "y": 0},
                "properties": {
                    "curiosity_target_entity_id": "tree",
                    "safety_target_entity_id": "shelter",
                },
            }
            store = FakeStore([
                npc,
                {"id": "tree", "type": "place", "region_id": "r0", "position": {"x": 5, "y": 0}, "properties": {}},
                {"id": "shelter", "type": "place", "region_id": "r0", "position": {"x": 2, "y": 0}, "properties": {}},
            ])
            needs = FakeNeedState({"safety": 0.60, "energy": 0.0, "social": 0.0, "curiosity": 0.90})
            proposals = FakeProposalLedger()
            plans = FakePlanScheduler(store)
            composite = TwoPassComposite()
            executor = FakeExecutor()
            scheduler = NpcReorderingNeedScheduler(
                Path(tmpdir) / "needs.jsonl",
                proposals,
                plans,
                npc_ids=["nov"],
                threshold=0.70,
                cooldown_ticks=10,
                need_state_provider=needs,
                composite_strategy_provider=composite,
                strategy_compiler=NpcStrategyCompiler(),
                strategy_executor=executor,
            )

            first = scheduler.evaluate_tick(1)[0]
            self.assertTrue(first["horizon_reordered"])
            self.assertEqual(first["original_need"], "curiosity")
            self.assertEqual(first["need"], "safety")
            self.assertEqual(first["selected_target_entity_id"], "shelter")

            # Real state after the prerequisite: safety pressure is gone; curiosity remains.
            needs.values = {"safety": 0.10, "energy": 0.0, "social": 0.0, "curiosity": 0.90}
            second = scheduler.evaluate_tick(2)[0]
            self.assertFalse(second["horizon_reordered"])
            self.assertEqual(second["original_need"], "curiosity")
            self.assertEqual(second["need"], "curiosity")
            self.assertEqual(second["selected_target_entity_id"], "tree")
            self.assertEqual(len(executor.calls), 2)

    def test_original_goal_can_disappear_after_prerequisite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            npc = {
                "id": "nov", "type": "human", "region_id": "r0", "position": {"x": 0, "y": 0},
                "properties": {"curiosity_target_entity_id": "tree", "safety_target_entity_id": "shelter"},
            }
            store = FakeStore([
                npc,
                {"id": "tree", "type": "place", "region_id": "r0", "position": {"x": 5, "y": 0}, "properties": {}},
                {"id": "shelter", "type": "place", "region_id": "r0", "position": {"x": 2, "y": 0}, "properties": {}},
            ])
            needs = FakeNeedState({"safety": 0.60, "energy": 0.0, "social": 0.0, "curiosity": 0.90})
            scheduler = NpcReorderingNeedScheduler(
                Path(tmpdir) / "needs.jsonl", FakeProposalLedger(), FakePlanScheduler(store),
                npc_ids=["nov"], threshold=0.70, cooldown_ticks=10, need_state_provider=needs,
                composite_strategy_provider=TwoPassComposite(), strategy_compiler=NpcStrategyCompiler(),
                strategy_executor=FakeExecutor(),
            )
            first = scheduler.evaluate_tick(1)[0]
            self.assertEqual(first["need"], "safety")

            needs.values = {"safety": 0.10, "energy": 0.0, "social": 0.0, "curiosity": 0.20}
            self.assertEqual(scheduler.evaluate_tick(2), [])


if __name__ == "__main__":
    unittest.main()
