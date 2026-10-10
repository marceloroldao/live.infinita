"""Synthetic contextual contracts only; no production writes."""
import unittest
from nov_animal_approach_context import PROFILE,payload,recover,recommend
from nov_spatial_memory_sync import _observation_id
class ContextTests(unittest.TestCase):
    def ctx(self,blocked=False,stamp=3000):
        return {"profile":PROFILE,"sweep_m":4.0,"blocked_ahead":blocked,"sample_logical_ms":stamp}
    def candidates(self,blocked=False):
        return [{"entity_id":"w:rabbit:0","distance_m":16,"context":self.ctx(blocked)},
                {"entity_id":"w:rabbit:1","distance_m":22.36,"context":self.ctx(False)}]
    def entry(self,i,far,success,stamp,blocked=False):
        r={"id":"w:animal-approach:contract:"+str(i),"world_id":"w","entity_id":"w:rabbit:"+str(int(far)),
           "started_ms":stamp-100,"ended_ms":stamp,"result":"approached" if success else "no_progress","distance_m":16 if far and success else 5,
           "initial_observed_remaining_m":22.36 if far else 16,"final_observed_remaining_m":6.4 if success else 10,"revision":1,
           "censored":False,"learning_eligible":True,"capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False}
        value={"approach":r,"context":self.ctx(blocked,stamp-100),"contacts":0 if success else 10}
        return dict(value,observation_id=_observation_id(payload(value)["event"]))
    def known(self,blocked=False):
        return [self.entry(0,False,False,1000,blocked),self.entry(1,True,True,1000),
                self.entry(2,False,False,2000,blocked),self.entry(3,True,True,2000)]
    def test_matching_context_changes_choice(self):
        d=recommend(self.candidates(True),self.known(True),"w",3000)
        self.assertEqual(d["entity_id"],"w:rabbit:1");self.assertEqual(d["source"],"recovered-contextual-evidence")
    def test_changed_obstacle_context_rejects_old_preference(self):
        c=self.candidates();c[1]["context"]=self.ctx(True)
        d=recommend(c,self.known(True),"w",3000)
        self.assertEqual(d["entity_id"],"w:rabbit:0");self.assertEqual(d["reason"],"unseen_physical_context")
    def test_failure_drives_balanced_reassessment_without_ram(self):
        entries=self.known()+[self.entry(4,True,False,2500)]
        self.assertEqual(recommend(self.candidates(),entries,"w",3000)["entity_id"],"w:rabbit:0")
        entries.append(self.entry(5,False,True,2600))
        d=recommend(self.candidates(),entries,"w",3000)
        self.assertEqual(d["entity_id"],"w:rabbit:1");self.assertEqual(d["source"],"recovered-failure-reassessment")
        entries.append(self.entry(6,True,False,2700))
        self.assertEqual(recommend(self.candidates(),entries,"w",3000)["entity_id"],"w:rabbit:0")
        entries.append(self.entry(7,False,True,2800))
        d=recommend(self.candidates(),entries,"w",3000)
        self.assertEqual(d["entity_id"],"w:rabbit:0");self.assertEqual(d["reason"],"same_choice_as_perception")
    def test_forged_or_duplicate_context_rejected(self):
        entries=self.known();entries[0]["context"]["blocked_ahead"]=True
        with self.assertRaises(ValueError):recommend(self.candidates(),entries,"w",3000)
        entries=self.known();entries.append(dict(entries[0]))
        with self.assertRaises(ValueError):recommend(self.candidates(),entries,"w",3000)
    def test_context_clock_and_profile_validation(self):
        for k,v in (("sample_logical_ms",3301),("sample_logical_ms",2000),("profile","unknown"),("sweep_m",True),("blocked_ahead",1)):
            c=self.candidates();c[0]["context"][k]=v
            with self.assertRaises(ValueError):recommend(c,self.known(),"w",3000)
    def test_future_evidence_cannot_trigger_reassessment(self):
        entries=self.known()+[self.entry(4,True,False,4000)]
        self.assertEqual(recommend(self.candidates(),entries,"w",3000)["source"],"recovered-contextual-evidence")
    def test_core_envelope_verified(self):
        entry=self.known()[0];value={k:v for k,v in entry.items() if k!="observation_id"}
        request=payload(value);envelope=dict(request,observation_id=entry["observation_id"])
        self.assertEqual(recover({"semantic_projection":False,"items":[envelope]},"w"),[entry])
        envelope["provenance"]["outcome"]["contacts"]+=1
        with self.assertRaises(ValueError):recover({"semantic_projection":False,"items":[envelope]},"w")
    def test_censored_and_unmeasured_facts_rejected(self):
        entry=self.known()[0];value={k:v for k,v in entry.items() if k!="observation_id"}
        value["approach"].update(result="clock_unavailable",censored=True,learning_eligible=False)
        with self.assertRaises(ValueError):payload(value)
    def test_duplicate_recovery_rejected(self):
        entry=self.known()[0];request=payload({k:v for k,v in entry.items() if k!="observation_id"})
        e=dict(request,observation_id=entry["observation_id"])
        with self.assertRaises(ValueError):recover({"semantic_projection":False,"items":[e,e]},"w")
    def test_patterns_transfer_to_other_visible_ids(self):
        candidates=self.candidates(True)
        candidates[0]["entity_id"]="w:rabbit:8";candidates[1]["entity_id"]="w:rabbit:9"
        self.assertEqual(recommend(candidates,self.known(True),"w",3000)["entity_id"],"w:rabbit:9")
    def test_empty_memory_abstains(self):
        self.assertEqual(recommend(self.candidates(),[],"w",3000)["source"],"perception")
if __name__=="__main__":unittest.main()
