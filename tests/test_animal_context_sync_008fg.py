"""Synthetic contracts; isolated files and fake receipts, no live writes."""
import json,tempfile,unittest
from pathlib import Path
from copy import deepcopy
from hashlib import sha256
from nov_animal_context_sync import sync_once,SCHEMA,NATIVE_PROFILE
from nov_animal_approach_context import PROFILE,payload
from nov_spatial_memory_sync import _observation_id
class ContextBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source,self.world,self.checkpoint,self.recall,self.public=[self.root/n for n in ("source","world","checkpoint","recall","public")]
        self.world.write_text('{"world_id":"w"}')
        self.rows=[]
        for i in range(5):
            a={"id":"w:animal-approach:contract:"+str(i),"world_id":"w","entity_id":"w:rabbit:0","started_ms":1000.0,"ended_ms":2000.0,
               "result":"approached","distance_m":3.6,"initial_observed_remaining_m":10.0,"final_observed_remaining_m":6.4,"revision":1.0,
               "censored":False,"learning_eligible":True,"capture":False,"contains_prediction":False,"absence_claim":False,"world_write_authority":False}
            self.rows.append({"approach":a,"context":{"profile":NATIVE_PROFILE,"sweep_m":4.0,"blocked_ahead":False,"sample_logical_ms":1000.0},"contacts":0.0})
        self.items=[];self.write()
    def write(self):
        raw=json.dumps({"schema":SCHEMA,"records":self.rows})
        self.source.write_text(json.dumps({"payload":raw,"sha256":sha256(raw.encode()).hexdigest()}))
    def send(self,request):
        identity=_observation_id(request["event"]);duplicate=any(e["observation_id"]==identity for e in self.items)
        if not duplicate:self.items.append(dict(deepcopy(request),observation_id=identity))
        return {"observation_id":identity,"stored":not duplicate,"duplicate":duplicate,"association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}
    def fetch(self):return {"semantic_projection":False,"items":self.items}
    def run_sync(self,**kw):
        return sync_once(self.source,self.world,self.checkpoint,self.recall,self.public,send=kw.get("send",self.send),fetch=kw.get("fetch",self.fetch),now=lambda:3000)
    def test_batch_dedup_and_cold_recovery(self):
        self.assertEqual(self.run_sync()["acked_this_poll"],4)
        self.assertEqual(self.run_sync()["acked_this_poll"],1)
        self.recall.unlink();d=self.run_sync()
        self.assertEqual(d["acked_this_poll"],0);self.assertEqual(d["cached_recovered"],5)
        self.assertFalse(d["decision_use"]);self.assertFalse(d["capture"]);self.assertFalse(d["world_write_authority"])
        self.assertTrue(all(type(e["contacts"]) is int for e in json.loads(self.recall.read_text())["entries"]))
    def test_direct_profile_not_ingested(self):
        self.rows[0]["context"]["profile"]=PROFILE;self.write()
        with self.assertRaises(ValueError):self.run_sync()
        self.assertFalse(self.items)
    def test_direct_core_facts_retained_but_not_native_recall(self):
        old=deepcopy(self.rows[0]);old["contacts"]=0;old["context"]["profile"]=PROFILE;old["approach"]["id"]+=":direct"
        req=payload(old);self.send(req);d=self.run_sync()
        self.assertEqual(len(self.items),5);self.assertEqual(d["cached_recovered"],4)
        self.assertEqual(self.items[0]["provenance"]["outcome"]["context"]["profile"],PROFILE)
    def test_checksum_duplicates_and_symlink(self):
        d=json.loads(self.source.read_text());d["sha256"]="bad";self.source.write_text(json.dumps(d))
        with self.assertRaises(Exception):self.run_sync()
        self.rows.append(deepcopy(self.rows[0]));self.write()
        with self.assertRaises(Exception):self.run_sync()
        link=self.root/"link";link.symlink_to(self.source)
        with self.assertRaises(Exception):sync_once(link,self.world,self.checkpoint,self.recall,None,send=self.send,fetch=self.fetch)
        self.assertFalse(self.items)
    def test_invalid_or_censored_contexts(self):
        for kind,key,value in [("context","sample_logical_ms",1001),("context","blocked_ahead",1),("approach","capture",True),
                              ("approach","censored",True),("approach","distance_m",0),("root","contacts",0.5),("root","contacts",True)]:
            original=deepcopy(self.rows)
            with self.subTest(key=key):
                obj=self.rows[0] if kind=="root" else self.rows[0][kind];obj[key]=value;self.write()
                with self.assertRaises(Exception):self.run_sync()
            self.rows=original
        self.assertFalse(self.items)
    def test_failed_and_non_durable_receipts(self):
        for key,val in [("observation_id","bad"),("backend","memory"),("stored",False)]:
            self.items=[]
            def bad(req):
                receipt=self.send(req);receipt[key]=val;return receipt
            with self.assertRaises(Exception):self.run_sync(send=bad)
            self.assertFalse(self.checkpoint.exists())
    def test_partial_failure_resumes(self):
        def fail(req):
            if len(self.items)==2:raise RuntimeError("temporary")
            return self.send(req)
        with self.assertRaises(RuntimeError):self.run_sync(send=fail)
        self.assertEqual(json.loads(self.checkpoint.read_text())["confirmed"],2)
        self.assertEqual(self.run_sync()["acked_this_poll"],3)
    def test_mutated_fact_and_cache_rejected(self):
        self.run_sync();self.rows[0]["approach"]["distance_m"]+=1;self.write()
        with self.assertRaises(Exception):self.run_sync()
        self.rows[0]["approach"]["distance_m"]-=1;self.write()
        d=json.loads(self.recall.read_text());d["entries"][0]["observation_id"]="bad";self.recall.write_text(json.dumps(d))
        with self.assertRaises(Exception):self.run_sync()
    def test_receipt_does_not_replace_recovery(self):
        d=self.run_sync(fetch=lambda:{"semantic_projection":False,"items":[]})
        self.assertEqual(d["confirmed_total"],4);self.assertEqual(d["cached_recovered"],0)
    def test_wrong_world_skipped(self):
        self.world.write_text('{"world_id":"other"}')
        self.assertEqual(self.run_sync()["eligible_in_source"],0)
if __name__=="__main__":unittest.main()
