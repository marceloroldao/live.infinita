"""Component contract tests; synthetic rows never enter production."""
import json
from pathlib import Path
import tempfile
import unittest
from copy import deepcopy
from nov_navigation_pattern_sync import PROFILE, SCHEMA, sync_once, payload, PatternSyncError
from nov_spatial_memory_sync import _observation_id

class PatternBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source,self.world,self.checkpoint,self.recall=[self.root/n for n in ("source","world","checkpoint","recall")]
        self.world.write_text(json.dumps({"world_id":"w"}))
        self.rows=[{"attempt_id":"attempt"+str(i),"world_id":"w","observer":"nov","profile":PROFILE,
                    "context":PROFILE+"|w|local-clear-v1:255:254","side":1 if i%2==0 else -1,
                    "outcome":"contour_completed","distance_m":100+i,"initial_remaining_m":15,
                    "physical_attempt":True,"contains_prediction":False,"ended_at_unix":1000+i,
                    "exploration":i>0,"completion_basis":"executed_exit","exit_progress_m":1.0} for i in range(4)]
        self.write()
        self.items=[]
    def write(self):
        self.source.write_text(json.dumps({"schema":SCHEMA,"profile":PROFILE,"rows":self.rows}))
    def send(self, request):
        identity=_observation_id(request["event"])
        duplicate=any(r["observation_id"]==identity for r in self.items)
        if not duplicate:self.items.append(dict(deepcopy(request),observation_id=identity))
        return {"observation_id":identity,"stored":not duplicate,"duplicate":duplicate,
                "association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}
    def fetch(self):
        return {"semantic_projection":False,"items":self.items}
    def run_sync(self, **kwargs):
        return sync_once(self.source,self.world,self.checkpoint,self.recall,
                         send=kwargs.get("send",self.send),fetch=kwargs.get("fetch",self.fetch),now=lambda:2000)
    def test_idempotent_recovery_and_cost_link(self):
        self.assertEqual(self.run_sync()["acked"],4)
        self.recall.unlink()
        self.assertEqual(self.run_sync()["acked"],0)
        entries=json.loads(self.recall.read_text())["entries"]
        self.assertEqual(len(entries),4)
        for row in entries:
            identity=row.pop("observation_id")
            self.assertEqual(identity,_observation_id(payload(row)["event"]))
    def test_godot_integral_float_side_is_normalized(self):
        for row in self.rows:row["side"]=float(row["side"])
        self.write()
        self.assertEqual(self.run_sync()["acked"],4)
        self.assertTrue(all(type(r["provenance"]["outcome"]["side"]) is int for r in self.items))
        self.assertEqual(self.run_sync()["acked"],0)
    def test_predictions_and_censored_are_rejected(self):
        for field,value in [("contains_prediction",True),("physical_attempt",False),("outcome","interrupted")]:
            with self.subTest(field=field):
                original=deepcopy(self.rows)
                self.rows[0][field]=value;self.write()
                with self.assertRaises(PatternSyncError):self.run_sync()
                self.rows=original
        self.assertFalse(self.items)
    def test_wrong_world_is_not_ingested(self):
        self.world.write_text(json.dumps({"world_id":"other"}))
        self.assertEqual(self.run_sync()["acked"],0)
    def test_forged_recovered_measurement_is_rejected(self):
        self.run_sync()
        self.items[0]["provenance"]["outcome"]["distance_m"]+=1
        with self.assertRaises(PatternSyncError):self.run_sync()
    def test_receipt_failure_cannot_become_confirmation(self):
        def bad(request):
            receipt=self.send(request);receipt["observation_id"]="bad";return receipt
        with self.assertRaises(Exception):self.run_sync(send=bad)
        self.assertFalse(self.checkpoint.exists())
        self.assertEqual(self.run_sync()["acked"],4) # Duplicate real receipts remain idempotent.
    def test_partial_failure_resumes(self):
        def failing(request):
            if len(self.items)==2:raise RuntimeError("temporary")
            return self.send(request)
        with self.assertRaises(RuntimeError):self.run_sync(send=failing)
        self.assertEqual(json.loads(self.checkpoint.read_text())["confirmed"],2)
        self.assertEqual(self.run_sync()["acked"],2)
        self.assertEqual(len(self.items),4)
    def test_duplicate_or_changed_attempt_rejected(self):
        self.rows.append(deepcopy(self.rows[0]));self.write()
        with self.assertRaises(PatternSyncError):self.run_sync()
        self.rows.pop();self.write();self.run_sync()
        self.rows[0]["distance_m"]+=1;self.write()
        with self.assertRaises(PatternSyncError):self.run_sync()
    def test_profile_numeric_and_symlink_validation(self):
        for field,value in [("profile","different"),("side",True),("distance_m",float("nan")),("initial_remaining_m",0)]:
            with self.subTest(field=field):
                original=deepcopy(self.rows);self.rows[0][field]=value;self.write()
                with self.assertRaises((PatternSyncError,ValueError)):self.run_sync()
                self.rows=original
        self.write()
        link=self.root/"link";link.symlink_to(self.source)
        with self.assertRaises(PatternSyncError):
            sync_once(link,self.world,self.checkpoint,self.recall,send=self.send,fetch=self.fetch)

    def test_exit_requires_measured_forward_progress(self):
        for value in [0.74, True, -1, float("nan")]:
            with self.subTest(progress=value):
                self.rows[0]["exit_progress_m"]=value;self.write()
                with self.assertRaises((PatternSyncError,ValueError)):self.run_sync()
        self.assertFalse(self.items)
    def test_failure_requires_matching_physical_basis(self):
        for outcome,basis in [("blocked","executed_exit"),("stuck_recovery","physical_collision")]:
            with self.subTest(outcome=outcome):
                self.rows[0].update(outcome=outcome,completion_basis=basis);self.write()
                with self.assertRaises(PatternSyncError):self.run_sync()
        self.assertFalse(self.items)

if __name__=="__main__":unittest.main()
