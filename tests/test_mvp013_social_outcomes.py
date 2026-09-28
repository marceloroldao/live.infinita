from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for item in (str(ROOT), str(RUNTIME)):
    if item not in sys.path:
        sys.path.insert(0, item)

from npc_need_dynamics import NpcNeedDynamics  # noqa: E402
from npc_need_outcomes import NpcNeedOutcomeProcessor  # noqa: E402
from npc_composite_strategy_outcomes import NpcCompositeStrategyOutcomeProcessor  # noqa: E402
from npc_strategy_experience import NpcStrategyExperience  # noqa: E402
from plan_ledger import PlanLedger  # noqa: E402
from tests.test_mvp013_social_opportunity import nov, actor  # noqa: E402
from tests.test_npc_need_scheduler import FakeStore  # noqa: E402
from tests.test_npc_composite_strategy_outcomes import FakeStrategyExecutor, FakePlanLedger, FakeNeedOutcomes  # noqa: E402


class SocialOutcomeTests(unittest.TestCase):
    def complete(self, ledger):
        intent = {
            "intent": "move_to_entity",
            "actor_entity_id": "nov",
            "target_entity_id": "friend",
            "need": "social",
            "target_evidence_source": "observed_social_capability",
        }
        plan = ledger.create(
            proposal_id="proposal_1", proposer_id="npc:nov",
            principal={"source": "npc_need", "actor_id": "nov",
                       "authority": "entity_agent", "subject_entity_id": "nov"},
            intent=intent,
            plan={
                "intent_type": "move_to_entity", "actor_entity_id": "nov",
                "source_region_id": "clearing", "goal_region_id": "clearing",
                "region_path": ["clearing"],
                "steps": [{"step_index": 0, "kind": "goal", "intent": intent,
                           "expected_region_id": "clearing", "goal_region_id": "clearing"}],
            },
        )
        running = ledger.transition(plan["plan_id"], "running")
        return ledger.mark_step_completed(
            running["plan_id"], step_index=0,
            mutation_decision_id="decision_1", world_event_id="event_1",
            state_hash="hash_1",
        )

    def test_arrival_audits_encounter_but_never_fabricates_satisfaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            you = nov()
            you["position"]["x"] = 10
            store = FakeStore([you, actor("friend")])
            dynamics = NpcNeedDynamics(root / "need-state.json", store, npc_ids=["nov"])
            dynamics.advance_tick(1)
            ledger = PlanLedger(root / "plans.jsonl")
            plan = self.complete(ledger)
            processor = NpcNeedOutcomeProcessor(root / "outcomes.jsonl", ledger, dynamics)
            before = dynamics.get_needs("nov")["social"]
            row = processor.process_completed()[0]
            self.assertEqual(row["status"], "encounter_observed")
            self.assertTrue(row["social_encounter_evidence"]["co_present"])
            self.assertFalse(row["social_encounter_evidence"]["social_interaction_confirmed"])
            self.assertEqual(dynamics.get_needs("nov")["social"], before)
            self.assertIsNone(row["learning"])
            self.assertIsNone(row["episode_id"])
            self.assertEqual(processor.process_completed(), [])
            self.assertIsNone(processor.get_applied(plan["plan_id"]))
            restarted = NpcNeedOutcomeProcessor(processor.path, ledger, dynamics)
            self.assertEqual(restarted.process_completed(), [])

    def test_missing_target_is_not_an_encounter_or_satisfaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = FakeStore([nov()])
            dynamics = NpcNeedDynamics(root / "state.json", store, npc_ids=["nov"])
            dynamics.advance_tick(1)
            ledger = PlanLedger(root / "plans.jsonl")
            self.complete(ledger)
            processor = NpcNeedOutcomeProcessor(root / "outcomes.jsonl", ledger, dynamics)
            before = dynamics.get_needs("nov")["social"]
            row = processor.process_completed()[0]
            self.assertEqual(row["status"], "encounter_unverified")
            self.assertEqual(row["social_encounter_evidence"]["reason"], "entity_missing")
            self.assertEqual(dynamics.get_needs("nov")["social"], before)

    def test_composite_arrival_does_not_train_strategy_as_social_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            execution = {
                "strategy_execution_id": "s1", "status": "completed",
                "strategy_plan": {"need": "social", "target_entity_id": "friend",
                                  "actor_entity_id": "nov", "strategy_id": "via_clearing"},
                "completed_phases": [
                    {"phase_index": 0, "kind": "move_to_entity",
                     "child_plan_id": "p1", "completed_logical_tick": 3},
                ],
            }
            plans = FakePlanLedger({"p1": {
                "plan_id": "p1", "intent": {
                    "need": "social", "target_entity_id": "friend",
                    "target_evidence_source": "observed_social_capability",
                },
                "started_logical_tick": 1, "completed_logical_tick": 3,
            }})
            experience = NpcStrategyExperience(root / "experience.json", min_samples=1)
            proc = NpcCompositeStrategyOutcomeProcessor(
                root / "composite.jsonl", FakeStrategyExecutor([execution]),
                plans, FakeNeedOutcomes([]), experience,
            )
            rows = proc.process_completed()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["status"], "social_goal_no_reward")
            self.assertEqual(proc.process_completed(), [])
            self.assertIsNone(experience.strategy_stats(
                "nov", "social", "friend", "via_clearing",
                {"period": "day", "weather": "clear", "region_id": "clearing"},
            ))


if __name__ == "__main__":
    unittest.main()
