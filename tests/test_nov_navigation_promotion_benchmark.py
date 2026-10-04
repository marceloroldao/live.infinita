import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("promotion_benchmark",
    Path(__file__).resolve().parents[1]/"tools/benchmark_navigation_promotion_008cq.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class PromotionEvidenceTests(unittest.TestCase):
    def data(self):
        session = "a"*32
        identities = [session+":"+str(n) for n in (1,2,3)]
        summary = {"key":"5,0|0,0","to":[0.0,1.0]}
        row = {"summary":summary,"decision_ids":identities}
        evidence = {}
        for n,identity in enumerate(identities,1):
            evidence[identity] = {"working_memory_session":session,"decision_serial":n,
                "working_memory_key":summary["key"],"working_memory_changed_choice":True,
                "outcome":"step_reached","collisions":0,"selected":[0.0,1.0],
                "end":[0.0,1.0],"perception":{"without_working_memory":[1.0,0.0]}}
        return {"promotions":{"entries":[row]},"promotion_evidence_actions":evidence}
    def test_completed_distinct_causal_actions_support_promotion(self):
        self.assertEqual(module.verify_promotions(self.data()),1)
    def test_counter_alone_cannot_replace_causal_choice(self):
        data=self.data()
        action=next(iter(data["promotion_evidence_actions"].values()))
        action["perception"]["without_working_memory"]=action["selected"].copy()
        with self.assertRaises(AssertionError): module.verify_promotions(data)
    def test_blocked_partial_or_other_session_cannot_support_promotion(self):
        for change in ({"outcome":"blocked"},{"collisions":1},{"end":[0.0,0.5]},
                       {"working_memory_session":"b"*32},{"working_memory_changed_choice":False}):
            data=self.data()
            next(iter(data["promotion_evidence_actions"].values())).update(change)
            with self.subTest(change=change), self.assertRaises(AssertionError):
                module.verify_promotions(data)
    def test_evidence_must_match_promoted_step(self):
        data=self.data()
        data["promotions"]["entries"][0]["summary"]["to"]=[1.0,0.0]
        with self.assertRaises(AssertionError): module.verify_promotions(data)


class EnvironmentValidationTests(unittest.TestCase):
    def data(self):
        import json
        return json.loads((Path(__file__).resolve().parents[1]/
            "docs/NAVIGATION_ENVIRONMENT_RESULT_008CS.json").read_text())["after"]
    def test_archived_complete_physical_trials_validate(self):
        self.assertTrue(module.validate_environment(self.data()))
    def test_collision_nonarrival_missing_or_unnecessary_detour_rejects(self):
        for mutation in ("collision","arrival","missing","detour"):
            data=self.data()
            if mutation=="collision": data["results"][0]["collisions"]=1
            elif mutation=="arrival": data["results"][0]["reached"]=False
            elif mutation=="missing": data["results"].pop()
            else:
                for row in data["results"]:
                    if row["variant"]=="opened_U": row["distance_m"]=7.0
            with self.subTest(mutation=mutation), self.assertRaises(AssertionError):
                module.validate_environment(data)
