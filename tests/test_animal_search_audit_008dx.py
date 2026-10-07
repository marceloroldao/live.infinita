import copy
import importlib.util
import pathlib
import unittest

p = pathlib.Path(__file__).resolve().parents[1] / "tools/audit_animal_search_008dx.py"
spec = importlib.util.spec_from_file_location("audit", p)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

class AuditTests(unittest.TestCase):
    def setUp(self):
        world = "fixture"
        common = dict(world_id=world, world_write_authority=False, absence_claim=False,
                      last_error=None, generated_at_unix=100)
        self.intent = dict(common, schema="live-infinita-nov-animal-search-intent/v1",
                           source="native_bounded_animal_search", decision_use=True,
                           active=False, intent={}, results=[],logical_time_ms=100000,
                           counts={a:dict(started=0,confirmed=0,not_observed=0,aborted=0) for a in mod.ARMS})
        self.memory = dict(common, schema="live-infinita-nov-animal-memory/v1",
                           decision_use=False, verified_history=[], stored_and_recovered_encounters=0)
        self.prediction = dict(common, schema="live-infinita-nov-animal-search/v1",
                               source="verified_recalled_eye_encounters",decision_use=False,
                               counters={},paired_metrics={})
    def run_audit(self):
        return mod.audit(self.intent,self.memory,self.prediction,now=101)
    def test_expired_ack_grace_forecast_is_not_search_ready(self):
        self.prediction["forecasts"]=[dict(issued_ms=1000,expires_ms=61000)]
        result=self.run_audit()["search_readiness"]
        self.assertEqual(result["forecast_time_eligibility"]["expired"],1)
        self.assertEqual(result["status"],"no_forecast_with_sufficient_time")
    def test_minimum_remaining_time_and_next_strategy(self):
        self.prediction["forecasts"]=[dict(issued_ms=50000,expires_ms=110000),dict(issued_ms=70000,expires_ms=130000)]
        self.intent["counts"]["memory"].update(started=1,confirmed=1)
        result=self.run_audit()["search_readiness"]
        self.assertEqual(result["next_strategy"],"last_seen")
        self.assertEqual(result["forecast_time_eligibility"]["eligible_by_time"],1)
        self.assertEqual(result["forecast_time_eligibility"]["less_than_20_seconds_remaining"],1)
    def test_zero_trials_is_unknown_not_zero_precision(self):
        del self.memory["absence_claim"]
        r=self.run_audit()
        self.assertIsNone(r["bounded_search"]["arms"]["memory"]["confirmed_per_completed"])
        self.assertEqual(r["bounded_search"]["comparison_state"],"waiting_for_both_strategies")
    def test_active_attempt_is_excluded_from_completed_denominator(self):
        self.intent["counts"]["memory"].update(started=2,confirmed=1)
        self.intent.update(active=True,intent={"arm":"memory"})
        r=self.run_audit()
        self.assertEqual(r["bounded_search"]["arms"]["memory"]["confirmed_per_completed"],1)
        self.assertEqual(r["bounded_search"]["arms"]["memory"]["pending"],1)
    def test_stale_world_swap_and_authority_are_rejected(self):
        for key,value in [("generated_at_unix",0),("world_id","other"),("world_write_authority",True)]:
            original=self.memory[key];self.memory[key]=value
            with self.assertRaises(ValueError):self.run_audit()
            self.memory[key]=original
    def test_counter_inconsistency_is_rejected(self):
        self.intent["counts"]["last_seen"]["confirmed"]=1
        with self.assertRaises(ValueError):self.run_audit()
    def test_real_match_missing_window_and_duplicate_result(self):
        row=dict(id="fixture:animal-search:1",arm="memory",result="animal_seen",
                 entity_id="fixture:rabbit:0",started_ms=10,ended_ms=20,deadline_ms=100,
                 confirmed_by_eye_sensor=True,absence_claim=False)
        self.intent["results"]=[row];self.intent["counts"]["memory"].update(started=1,confirmed=1)
        self.assertEqual(self.run_audit()["bounded_search"]["recent_results"][0]["recovery_check"],"not_in_current_history_window")
        self.memory["verified_history"]=[dict(observation_id="actual-id",encounter=dict(entity_id=row["entity_id"],first_seen_ms=20))]
        self.assertEqual(self.run_audit()["bounded_search"]["recent_results"][0]["matching_recovered_encounter_ids"],["actual-id"])
        self.intent["results"].append(copy.deepcopy(row))
        with self.assertRaises(ValueError):self.run_audit()

if __name__ == "__main__":unittest.main()
