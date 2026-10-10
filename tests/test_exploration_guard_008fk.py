"""Synthetic budget contracts; actual interruption experiment is separate."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from copy import deepcopy
import test_cost_revalidation_008fj as fixtures
from nov_animal_exploration_guard import recommend_and_reserve,settle,GuardError
def contender(path,candidates,entries,queue):
    try:queue.put(recommend_and_reserve(path,candidates,entries,"w",400000))
    except Exception as e:queue.put({"error":type(e).__name__})
class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"guard";self.fixture=fixtures.CostRevalidationTests();self.fixture.setUp()
    def choose(self,stamp=400000):
        return recommend_and_reserve(self.path,self.fixture.candidates(stamp),self.fixture.entries(),"w",stamp)
    def interrupted(self,d,stamp=400000):
        return {"id":"w:animal-approach:interrupted:"+d["reservation_token"],"world_id":"w","entity_id":d["entity_id"],
                "started_ms":stamp,"ended_ms":None,"initial_observed_remaining_m":16,"result":"renderer_restart","distance_m":None,
                "censored":True,"learning_eligible":False,"capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False}
    def test_pending_survives_reopen_and_blocks_duplicate_start(self):
        d=self.choose();self.assertTrue(d["reservation_token"])
        self.assertEqual(self.choose()["reason"],"pending_reservation")
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        raw=json.loads(json.loads(self.path.read_text())["payload"])
        self.assertEqual(raw["worlds"]["w"]["reservations"][0]["status"],"reserved")
    def test_four_interruptions_consume_budget_without_learning(self):
        for i in range(4):
            stamp=400000+i*1000;d=self.choose(stamp);r=self.interrupted(d,stamp)
            self.assertEqual(settle(self.path,d["reservation_token"],r),"interrupted")
            self.assertEqual(settle(self.path,d["reservation_token"],r),"interrupted")
        d=self.choose(405000)
        self.assertIsNone(d["reservation_token"]);self.assertEqual(d["reason"],"exploration_budget_exhausted")
        self.assertEqual(d["source"],"perception");self.assertEqual(d["exploration_budget"]["used_attempts"],4)
    def test_completed_fact_releases_pending_but_keeps_used_slot(self):
        d=self.choose()
        e=self.fixture.fresh(30,False,True,401000)
        e["approach"]["started_ms"]=400000
        self.assertEqual(settle(self.path,d["reservation_token"],e["approach"]),"closed")
        self.assertEqual(self.choose(402000)["exploration_budget"]["used_attempts"],2)
    def test_failure_reassessment_uses_same_budget(self):
        rows=self.fixture.entries()+[self.fixture.fresh(40,True,False,350000)]
        for i in range(4):
            stamp=400000+i*1000
            d=recommend_and_reserve(self.path,self.fixture.candidates(stamp),rows,"w",stamp)
            self.assertEqual(d["source"],"recovered-failure-reassessment")
            settle(self.path,d["reservation_token"],self.interrupted(d,stamp))
        d=recommend_and_reserve(self.path,self.fixture.candidates(405000),rows,"w",405000)
        self.assertEqual(d["reason"],"exploration_budget_exhausted")
    def test_clock_rewind_and_next_epoch(self):
        d=self.choose()
        with self.assertRaises(GuardError):self.choose(399000)
        self.assertEqual(self.choose(700000)["reason"],"pending_reservation")
        settle(self.path,d["reservation_token"],self.interrupted(d))
        d=self.choose(701000);self.assertEqual(d["exploration_budget"]["used_attempts"],1)
    def test_changed_binding_and_unknown_token_rejected(self):
        d=self.choose();r=self.interrupted(d)
        bad=deepcopy(r);bad["entity_id"]="w:rabbit:9"
        with self.assertRaises(GuardError):settle(self.path,d["reservation_token"],bad)
        with self.assertRaises(GuardError):settle(self.path,"unknown",r)
        settle(self.path,d["reservation_token"],r);r["initial_observed_remaining_m"]=17
        with self.assertRaises(GuardError):settle(self.path,d["reservation_token"],r)
    def test_corrupt_symlink_and_failed_persistence_block_launch(self):
        d=self.choose();sealed=json.loads(self.path.read_text());sealed["sha256"]="bad";self.path.write_text(json.dumps(sealed))
        with self.assertRaises(GuardError):self.choose()
        link=self.path.parent/"link";link.symlink_to(self.path)
        with self.assertRaises(GuardError):recommend_and_reserve(link,self.fixture.candidates(400000),self.fixture.entries(),"w",400000)
        clean=self.path.parent/"clean"
        with patch("nov_animal_exploration_guard.write_checkpoint",side_effect=OSError("disk")):
            with self.assertRaises(OSError):recommend_and_reserve(clean,self.fixture.candidates(400000),self.fixture.entries(),"w",400000)
        self.assertFalse(clean.exists())
    def test_concurrent_reservations_allow_only_one_pending(self):
        import multiprocessing as mp
        ctx=mp.get_context("fork");queue=ctx.Queue()
        args=(self.path,self.fixture.candidates(400000),self.fixture.entries(),queue)
        processes=[ctx.Process(target=contender,args=args) for _ in range(2)]
        for p in processes:p.start()
        for p in processes:p.join(10);self.assertEqual(p.exitcode,0)
        results=[queue.get(timeout=3) for _ in range(2)]
        self.assertEqual(sum(bool(r.get("reservation_token")) for r in results),1)
        self.assertEqual(sum(r.get("reason")=="pending_reservation" for r in results),1)
if __name__=="__main__":unittest.main()
