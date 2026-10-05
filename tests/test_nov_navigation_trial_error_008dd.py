import copy
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/"tools/benchmark_navigation_trial_error_008dd.py"
spec=importlib.util.spec_from_file_location("causality_benchmark",path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CausalityValidationTests(unittest.TestCase):
    def rows(self):
        return [{"variant":v,"mode":m,"trial":t,"reached":True,"remaining_goal_m":0.0,
            "collisions":0,"route_plan_builds":0,"loaded_knowledge":0 if m=="without_memory" else 1,
            "selected_observation_ids":[],"verified_causal_ram_actions":0,
            "verified_causal_memoria_actions":0,"actions":[]}
            for v in ("unchanged_U","opened_U","remembered_step_blocked")
            for m in ("without_memory","with_trained_ram","after_restart_memoria") for t in (1,2)]
    def test_agreement_cannot_support_a_claimed_memory_effect(self):
        rows=self.rows()
        row=next(r for r in rows if r["mode"]=="after_restart_memoria")
        row["actions"]=[{"outcome":"step_reached","selected":[1,0],
            "decision_source":"memoria.ia","perception":{"without_memoria":[1,0]}}]
        row["verified_causal_memoria_actions"]=1
        with self.assertRaises(AssertionError):module.validate_results(rows,1,{"known"})
        row["verified_causal_memoria_actions"]=0
        self.assertTrue(module.validate_results(rows,1,{"known"}))
    def test_failed_attempt_is_not_a_successful_causal_reuse(self):
        rows=self.rows()
        row=next(r for r in rows if r["mode"]=="with_trained_ram")
        row["actions"]=[{"outcome":"blocked","selected":[0,1],"working_memory_changed_choice":True,
            "decision_source":"working-memory","perception":{"without_working_memory":[1,0]}}]
        row["verified_causal_ram_actions"]=1
        with self.assertRaises(AssertionError):module.validate_results(rows,1,{"known"})
    def test_selected_persistent_identity_must_have_an_api_receipt(self):
        rows=self.rows()
        row=next(r for r in rows if r["mode"]=="after_restart_memoria")
        row["selected_observation_ids"]=["unknown"]
        with self.assertRaises(AssertionError):module.validate_results(rows,1,{"known"})
    def test_different_knowledge_coverage_is_rejected(self):
        rows=self.rows()
        next(r for r in rows if r["mode"]=="with_trained_ram")["loaded_knowledge"]=2
        with self.assertRaises(AssertionError):module.validate_results(rows,1,{"known"})
    def test_missing_arm_cannot_be_a_matched_comparison(self):
        with self.assertRaises(AssertionError):module.validate_results(self.rows()[:-1],1,{"known"})

    def test_observed_route_search_invalidates_local_trial_error_control(self):
        rows=self.rows()
        rows[0]["route_plan_builds"]=1
        with self.assertRaises(AssertionError):module.validate_results(rows,1,{"known"})
    def test_non_arrival_is_preserved_as_an_experimental_result(self):
        rows=self.rows()
        rows[0]["reached"]=False
        rows[0]["remaining_goal_m"]=10.0
        self.assertTrue(module.validate_results(rows,1,{"known"}))
