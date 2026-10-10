"""Synthetic contracts; no live writes."""
import unittest
from copy import deepcopy
import test_approach_context_008ff as contracts
from nov_animal_cost_revalidation import recommend,EPOCH_MS
from nov_animal_approach_context import payload
from nov_spatial_memory_sync import _observation_id
class CostRevalidationTests(unittest.TestCase):
    def setUp(self):self.fixture=contracts.ContextTests()
    def candidates(self,now):
        values=self.fixture.candidates()
        for c in values:c["context"]["sample_logical_ms"]=now
        return values
    def entries(self):
        values=self.fixture.known()
        for e in values:
            e["approach"]["started_ms"]+=100000;e["approach"]["ended_ms"]+=100000;e["context"]["sample_logical_ms"]+=100000
            e["observation_id"]=_observation_id(payload({k:v for k,v in e.items() if k!="observation_id"})["event"])
        return values
    def fresh(self,i,far,success,stamp):
        e=self.fixture.entry(i,far,success,stamp)
        e["approach"]["distance_m"]=16 if far else 9.8
        e["observation_id"]=_observation_id(payload({k:v for k,v in e.items() if k!="observation_id"})["event"])
        return e
    def test_warm_preference_stays_until_new_epoch(self):
        self.assertEqual(recommend(self.candidates(200000),self.entries(),"w",200000)["entity_id"],"w:rabbit:1")
    def test_new_epoch_refreshes_successful_preference(self):
        d=recommend(self.candidates(400000),self.entries(),"w",400000)
        self.assertEqual(d["entity_id"],"w:rabbit:0");self.assertEqual(d["source"],"recovered-cost-revalidation")
        self.assertFalse(d["cost_revalidation"]["uses_ram_counter"])
    def test_four_measured_probes_then_recent_cost(self):
        rows=self.entries()
        for i,far in enumerate((False,True,False,True)):
            now=400000+i*12000
            d=recommend(self.candidates(now),deepcopy(rows),"w",now)
            self.assertEqual(d["entity_id"],"w:rabbit:"+str(int(far)))
            self.assertEqual(d["source"],"recovered-cost-revalidation")
            rows.append(self.fresh(10+i,far,True,now+1000))
        d=recommend(self.candidates(460000),rows,"w",460000)
        self.assertEqual(d["entity_id"],"w:rabbit:0");self.assertEqual(d["reason"],"same_choice_as_perception")
    def test_empty_one_or_three_contexts_do_not_start_refresh(self):
        c=self.candidates(400000)
        self.assertEqual(recommend(c,[],"w",400000)["source"],"perception")
        self.assertNotEqual(recommend(c[:1],self.entries(),"w",400000)["source"],"recovered-cost-revalidation")
        c.append({"entity_id":"w:rabbit:8","distance_m":8,"context":dict(c[0]["context"])})
        self.assertNotEqual(recommend(c,self.entries(),"w",400000)["source"],"recovered-cost-revalidation")
    def test_failure_reassessment_has_priority(self):
        rows=self.entries();rows.append(self.fresh(10,True,False,350000))
        self.assertEqual(recommend(self.candidates(400000),rows,"w",400000)["source"],"recovered-failure-reassessment")
    def test_forged_future_and_duplicate_facts(self):
        for mode in ("forged","duplicate","future"):
            rows=self.entries()
            if mode=="forged":rows[0]["context"]["blocked_ahead"]=True
            elif mode=="duplicate":rows.append(deepcopy(rows[0]))
            else:
                rows.append(self.fresh(10,False,True,500000))
                d=recommend(self.candidates(400000),rows,"w",400000)
                self.assertEqual(d["entity_id"],"w:rabbit:0");continue
            with self.assertRaises(ValueError):recommend(self.candidates(400000),rows,"w",400000)
    def test_order_and_new_identities(self):
        c=self.candidates(400000);c[0]["entity_id"]="w:rabbit:20";c[1]["entity_id"]="w:rabbit:21"
        self.assertEqual(recommend(c,self.entries(),"w",400000),recommend(c[::-1],self.entries()[::-1],"w",400000))
        self.assertEqual(recommend(c,self.entries(),"w",400000)["entity_id"],"w:rabbit:20")
    def test_previous_epoch_attempt_does_not_fill_budget(self):
        rows=self.entries();r=self.fresh(10,False,True,EPOCH_MS+10)
        r["approach"]["started_ms"]=EPOCH_MS-90;r["context"]["sample_logical_ms"]=EPOCH_MS-90
        r["observation_id"]=_observation_id(payload({k:v for k,v in r.items() if k!="observation_id"})["event"]);rows.append(r)
        d=recommend(self.candidates(400000),rows,"w",400000)
        counts=d["cost_revalidation"]["counts"]
        self.assertEqual(sum(v["measured_in_epoch"] for v in counts),0)
if __name__=="__main__":unittest.main()
