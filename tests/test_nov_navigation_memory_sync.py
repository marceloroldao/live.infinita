import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"apps/world-runtime"))
import nov_navigation_memory_sync as nav
from nov_spatial_memory_sync import _observation_id

class NavigationMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/"navigation.cfg"
        self.world = self.root/"world.json"
        self.checkpoint = self.root/"checkpoint.json"
        self.world.write_text(json.dumps({"world_id":"fixture-world"}))
        self.calls = []
        self.snapshot()
    def snapshot(self,count=1,to="Vector2(2.5, 0)"):
        self.source.write_text('[experience]\n\nfailures={\n"0,0>1,0": '+str(count)+'\n}\nroutes={\n"5,0|2,0": '+to+'\n}\n')
    def send(self,payload):
        self.calls.append(payload)
        return {"observation_id":_observation_id(payload["event"]),"stored":True,"duplicate":False,
                "association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}
    def run_sync(self,**kwargs):
        return nav.sync_once(self.source,self.world,self.checkpoint,send=self.send,**kwargs)
    def test_preview_reads_real_format_without_mutation(self):
        original = self.source.read_bytes()
        result = self.run_sync(preview=True)
        self.assertEqual(result["blocked_passages"],1)
        self.assertEqual(result["successful_steps"],1)
        self.assertEqual(original,self.source.read_bytes())
        self.assertFalse(self.checkpoint.exists())
        self.assertFalse(self.calls)
    def test_idempotence_and_changed_failure(self):
        self.assertEqual(self.run_sync()["acked"],2)
        self.assertEqual(self.run_sync()["acked"],0)
        self.snapshot(count=2)
        self.assertEqual(self.run_sync()["acked"],1)
        self.assertEqual(self.calls[-1]["provenance"]["summary"]["observed_count"],2)
        self.assertFalse(self.calls[-1]["provenance"]["selection_authority"])
        self.assertFalse(self.calls[-1]["provenance"]["chronological_episode"])
    def test_snapshot_whitespace_does_not_reinforce(self):
        self.run_sync()
        self.source.write_text(self.source.read_text()+"\n")
        self.assertEqual(self.run_sync()["acked"],0)
    def test_changed_success_is_new_evidence(self):
        self.run_sync()
        self.snapshot(to="Vector2(2.75, 0)")
        self.assertEqual(self.run_sync()["acked"],1)
        self.assertEqual(self.calls[-1]["provenance"]["summary"]["to"],[2.75,0.0])
    def test_bad_ack_never_checkpoints(self):
        def reject(payload):
            receipt = self.send(payload)
            receipt["observation_id"] = "wrong"
            return receipt
        with self.assertRaises(RuntimeError):
            nav.sync_once(self.source,self.world,self.checkpoint,send=reject)
        self.assertFalse(self.checkpoint.exists())
    def test_ack_must_confirm_store_or_duplicate(self):
        def empty_ack(payload):
            receipt = self.send(payload)
            receipt["stored"] = False
            return receipt
        with self.assertRaises(nav.NavigationSyncError):
            nav.sync_once(self.source,self.world,self.checkpoint,send=empty_ack)
        self.assertFalse(self.checkpoint.exists())
    def test_partial_failure_preserves_prior_ack(self):
        def fail_second(payload):
            if self.calls:
                raise RuntimeError("unavailable")
            return self.send(payload)
        with self.assertRaises(RuntimeError):
            nav.sync_once(self.source,self.world,self.checkpoint,send=fail_second)
        self.assertEqual(json.loads(self.checkpoint.read_text())["confirmed"],1)
        self.assertEqual(self.run_sync()["acked"],1)
    def test_world_change_is_rejected(self):
        self.run_sync()
        self.world.write_text(json.dumps({"world_id":"different"}))
        with self.assertRaises(nav.NavigationSyncError):
            self.run_sync()
    def test_partial_file_is_rejected_without_mutation(self):
        self.source.write_text('[experience]\nfailures={\n"0,0>1,0": 1\n}')
        with self.assertRaises(nav.NavigationSyncError):
            self.run_sync()
        self.assertFalse(self.checkpoint.exists())
    def test_bad_coordinate_and_count(self):
        for key,count in [("999999,0>1,0",1),("0,0>1,0",101)]:
            self.source.write_text('[experience]\nfailures={\n"'+key+'": '+str(count)+'\n}\nroutes={}\n')
            with self.assertRaises(nav.NavigationSyncError):
                self.run_sync()
    def test_symlink_rejected(self):
        link = self.root/"link.cfg"
        link.symlink_to(self.source)
        with self.assertRaises(nav.NavigationSyncError):
            nav.read_snapshot(link)
    def test_duplicate_keys_rejected(self):
        self.source.write_text('[experience]\nfailures={\n"0,0>1,0": 1,\n"0,0>1,0": 2\n}\nroutes={}\n')
        with self.assertRaises(nav.NavigationSyncError):
            self.run_sync()
    def test_no_more_than_two_records_per_run(self):
        self.source.write_text('[experience]\nfailures={\n"0,0>1,0": 1,\n"0,0>0,1": 1,\n"0,0>-1,0": 1\n}\nroutes={}\n')
        self.assertEqual(self.run_sync()["acked"],2)
        self.assertEqual(self.run_sync()["acked"],1)
        self.assertEqual(self.run_sync()["acked"],0)
if __name__ == "__main__":
    unittest.main()
