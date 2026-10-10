"""Synthetic contract fixtures; no production memory writes."""
import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from nov_animal_approach_sync import sync_once,payload,ApproachSyncError,SCHEMA,validate
from nov_spatial_memory_sync import _observation_id,SpatialMemorySyncError
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source,self.world,self.checkpoint,self.recall,self.public=[self.root/n for n in ("source","world","checkpoint","recall","public")]
        self.world.write_text('{"world_id":"w"}')
        self.rows=[{"id":"w:animal-approach:contract:"+str(i),"world_id":"w","entity_id":"w:rabbit:0","started_ms":1000.0,"ended_ms":2000.0,
            "result":"approached","distance_m":3.6,"initial_observed_remaining_m":10.0,"final_observed_remaining_m":6.4,"revision":1.0,
            "censored":False,"learning_eligible":True,"capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False} for i in range(5)]
        self.pending={};self.items=[];self.write()
    def write(self):
        raw=json.dumps({"schema":SCHEMA,"records":self.rows,"pending":self.pending})
        self.source.write_text(json.dumps({"payload":raw,"sha256":sha256(raw.encode()).hexdigest()}))
    def send(self,request):
        identity=_observation_id(request["event"]);duplicate=any(e["observation_id"]==identity for e in self.items)
        if not duplicate:self.items.append(dict(deepcopy(request),observation_id=identity))
        return {"observation_id":identity,"stored":not duplicate,"duplicate":duplicate,"association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}
    def fetch(self):return {"semantic_projection":False,"items":self.items}
    def run_sync(self,**kwargs):
        return sync_once(self.source,self.world,self.checkpoint,self.recall,self.public,send=kwargs.get("send",self.send),fetch=kwargs.get("fetch",self.fetch),now=lambda:3000)
    def test_batch_resume_dedup_and_cold_recovery(self):
        self.assertEqual(self.run_sync()["acked_this_poll"],4)
        self.assertEqual(self.run_sync()["acked_this_poll"],1)
        self.recall.unlink()
        d=self.run_sync()
        self.assertEqual(d["acked_this_poll"],0);self.assertEqual(d["cached_recovered"],5)
        self.assertFalse(d["decision_use"]);self.assertFalse(d["learned_hunting"])
        self.assertTrue(all(type(e["provenance"]["outcome"]["started_ms"]) is int for e in self.items))
    def test_censored_and_zero_movement_are_not_ingested(self):
        self.rows[0].update(result="clock_unavailable",censored=True,learning_eligible=False)
        self.rows[1].update(distance_m=0,learning_eligible=False)
        self.write();d=self.run_sync()
        self.assertEqual(d["eligible_in_source"],3);self.assertEqual(d["censored_in_source"],1);self.assertEqual(len(self.items),3)
    def test_pending_restart_stays_unmeasured(self):
        self.rows=[]
        self.pending={"id":"w:animal-approach:pending","world_id":"w","entity_id":"w:rabbit:0","started_ms":1000,"ended_ms":None,
          "initial_observed_remaining_m":10,"result":"renderer_restart","distance_m":None,"censored":True,"learning_eligible":False,
          "capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False}
        self.write();self.assertEqual(self.run_sync()["acked_this_poll"],0);self.assertFalse(self.items)
        self.rows=[self.pending];self.pending={};self.write()
        self.assertEqual(self.run_sync()["censored_in_source"],1)
    def test_checksum_and_duplicate_rejected(self):
        d=json.loads(self.source.read_text());d["sha256"]="bad";self.source.write_text(json.dumps(d))
        with self.assertRaises(ApproachSyncError):self.run_sync()
        self.rows.append(deepcopy(self.rows[0]));self.write()
        with self.assertRaises(ApproachSyncError):self.run_sync()
        self.assertFalse(self.items)
    def test_prediction_and_false_success_rejected(self):
        for field,value in [("capture",True),("contains_prediction",True),("distance_m",True),("distance_m",float("nan")),("started_ms",1.5),("final_observed_remaining_m",7),("censored",True),("revision",-1)]:
            original=deepcopy(self.rows)
            with self.subTest(field=field):
                self.rows[0][field]=value;self.write()
                with self.assertRaises((ApproachSyncError,ValueError)):self.run_sync()
            self.rows=original
        self.assertFalse(self.items)
    def test_wrong_world_skipped(self):
        self.world.write_text('{"world_id":"other"}')
        self.assertEqual(self.run_sync()["acked_this_poll"],0)
    def test_failed_ack_not_confirmed(self):
        def bad(request):
            receipt=self.send(request);receipt["observation_id"]="bad";return receipt
        with self.assertRaises(Exception):self.run_sync(send=bad)
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual(self.run_sync()["acked_this_poll"],4)
    def test_partial_failure_resumes(self):
        def fail(request):
            if len(self.items)==2:raise RuntimeError("temporary")
            return self.send(request)
        with self.assertRaises(RuntimeError):self.run_sync(send=fail)
        self.assertEqual(json.loads(self.checkpoint.read_text())["confirmed"],2)
        self.assertEqual(self.run_sync()["acked_this_poll"],3)
    def test_mutated_fact_and_forged_recovery_rejected(self):
        self.run_sync();self.rows[0]["distance_m"]+=1;self.write()
        with self.assertRaises(ApproachSyncError):self.run_sync()
        self.rows[0]["distance_m"]-=1;self.write()
        self.items[0]["provenance"]["outcome"]["distance_m"]+=1
        with self.assertRaises(ApproachSyncError):self.run_sync()
    def test_cache_identity_and_symlink_rejected(self):
        self.run_sync()
        d=json.loads(self.recall.read_text());d["entries"][0]["observation_id"]="bad";self.recall.write_text(json.dumps(d))
        with self.assertRaises(ApproachSyncError):self.run_sync()
        link=self.root/"link";link.symlink_to(self.source)
        with self.assertRaises(ApproachSyncError):sync_once(link,self.world,self.checkpoint,self.recall,None,send=self.send,fetch=self.fetch)
    def test_receipts_do_not_substitute_core_recovery(self):
        d=self.run_sync(fetch=lambda:{"semantic_projection":False,"items":[]})
        self.assertEqual(d["confirmed_total"],4)
        self.assertEqual(d["cached_recovered"],0)
        self.assertEqual(json.loads(self.recall.read_text())["entries"],[])
    def test_non_sqlite_receipt_rejected(self):
        def bad(request):
            d=self.send(request);d["backend"]="memory";return d
        with self.assertRaises((ApproachSyncError,SpatialMemorySyncError)):self.run_sync(send=bad)
        self.assertFalse(self.checkpoint.exists())
if __name__=="__main__":unittest.main()
