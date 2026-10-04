import copy
import importlib.util
from pathlib import Path
import unittest
from test_nov_navigation_episode_sync import episode

spec=importlib.util.spec_from_file_location("live_audit",Path(__file__).resolve().parents[1]/"tools/audit_live_navigation_008cm.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class LiveAuditTests(unittest.TestCase):
    def data(self,rows):
        return {"episodes":rows,"dropped_episodes":4}
    def test_agreement_is_not_causal_learning(self):
        row=episode();action=row["actions"][0]
        action["perception"]["without_memoria"]=action["selected"].copy()
        result=module.audit(self.data([row]))
        self.assertEqual(result["verified_causal_memoria"]["actions"],0)
        self.assertEqual(result["causal_claims_without_distinct_baseline"]["memoria"],1)
    def test_distinct_retrieved_step_and_completed_goal_are_separate(self):
        result=module.audit(self.data([episode()]))
        self.assertEqual(result["verified_causal_memoria"]["completed_steps"],1)
        self.assertEqual(result["verified_causal_memoria"]["goals_reached"],0)
        self.assertFalse(result["controlled_live_gain_measured"])
    def test_ram_interruption_not_counted_as_success(self):
        row=episode();action=row["actions"][0]
        action.update(decision_source="working-memory",memory_observation_id="",outcome="interrupted",
            working_memory_changed_choice=True,working_memory_key="5,0|0,0",reason="new_decision")
        action["perception"]["without_working_memory"]=[1.0,0.0]
        result=module.audit(self.data([row]))
        self.assertEqual(result["verified_causal_ram"]["actions"],1)
        self.assertEqual(result["verified_causal_ram"]["completed_steps"],0)
        self.assertEqual(result["verified_causal_memoria"]["actions"],0)
    def test_duplicate_snapshot_evidence_not_counted_twice(self):
        result=module.audit(self.data([episode(),copy.deepcopy(episode())]))
        self.assertEqual(result["all"]["actions"],1)
        self.assertEqual(result["duplicate_actions_ignored"],1)
    def test_conflicting_action_identity_rejected(self):
        changed=episode();changed["actions"][0]["end"]=[0,2]
        with self.assertRaisesRegex(ValueError,"identity_changed"):
            module.audit(self.data([episode(),changed]))
    def test_empty_window_keeps_unknown_times(self):
        result=module.audit(self.data([]))
        self.assertIsNone(result["window_started_at_unix"])
        self.assertEqual(result["all"]["actions"],0)
