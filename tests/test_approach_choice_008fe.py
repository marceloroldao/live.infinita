"""Synthetic policy contracts only; no production core writes."""
import unittest
from nov_animal_approach_candidate import recommend
from nov_animal_approach_sync import payload
from nov_spatial_memory_sync import _observation_id
class ChoiceTests(unittest.TestCase):
    def candidates(self):return [{"entity_id":"w:rabbit:0","distance_m":10.0},{"entity_id":"w:rabbit:1","distance_m":18.86}]
    def fact(self,index,distance,success,ended=1000):
        row={"id":"w:animal-approach:contract:"+str(index),"world_id":"w","entity_id":"w:rabbit:"+("0" if distance<12 else "1"),
            "started_ms":ended-500,"ended_ms":ended,"result":"approached" if success else "no_progress","distance_m":3.6 if success else 2.8,
            "initial_observed_remaining_m":distance,"final_observed_remaining_m":6.4 if success else 7.2,"revision":1,
            "censored":False,"learning_eligible":True,"capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False}
        return dict(row,observation_id=_observation_id(payload(row)["event"]))
    def entries(self):return [self.fact(0,10,False),self.fact(1,18.86,True),self.fact(2,10,False,2000),self.fact(3,18.86,True,2000)]
    def test_empty_memory_and_missing_support_abstain(self):
        for entries in ([],self.entries()[:3]):
            d=recommend(self.candidates(),entries,"w",3000)
            self.assertEqual(d["source"],"perception");self.assertEqual(d["entity_id"],"w:rabbit:0")
    def test_verified_failure_cost_changes_choice(self):
        d=recommend(self.candidates(),self.entries(),"w",3000)
        self.assertEqual(d["source"],"recovered-approach-evidence");self.assertEqual(d["entity_id"],"w:rabbit:1")
        self.assertEqual(len(d["observation_ids"]),4)
    def test_newest_balanced_experience_reverses_choice(self):
        entries=self.entries()+[self.fact(4,10,True,4000),self.fact(5,18.86,False,4000),self.fact(6,10,True,5000),self.fact(7,18.86,False,5000)]
        d=recommend(self.candidates(),entries,"w",6000)
        self.assertEqual(d["entity_id"],"w:rabbit:0")
        self.assertEqual(d["source"],"perception") # Same action does not claim a causal memory change.
    def test_future_evidence_cannot_steer(self):
        self.assertEqual(recommend(self.candidates(),self.entries(),"w",500)["source"],"perception")
    def test_forged_recovery_rejected(self):
        entries=self.entries();entries[0]["distance_m"]+=1
        with self.assertRaises(ValueError):recommend(self.candidates(),entries,"w",3000)
    def test_context_is_distance_pattern_not_animal_identity(self):
        candidates=[{"entity_id":"w:rabbit:8","distance_m":10},{"entity_id":"w:rabbit:9","distance_m":18.86}]
        self.assertEqual(recommend(candidates,self.entries(),"w",3000)["entity_id"],"w:rabbit:9")
    def test_invalid_candidates_rejected(self):
        for value in (True,float("nan"),25,6.5):
            candidates=self.candidates();candidates[0]["distance_m"]=value
            with self.assertRaises(ValueError):recommend(candidates,self.entries(),"w",3000)
        candidates=self.candidates();candidates[0]["entity_id"]="other:rabbit:0"
        with self.assertRaises(ValueError):recommend(candidates,self.entries(),"w",3000)
    def test_duplicate_evidence_cannot_meet_minimum(self):
        entries=self.entries();entries.append(dict(entries[0]))
        with self.assertRaises(ValueError):recommend(self.candidates(),entries,"w",3000)
    def test_no_candidates(self):
        self.assertIsNone(recommend([],[],"w",3000)["entity_id"])
if __name__=="__main__":unittest.main()
