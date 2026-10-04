import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"apps/world-runtime"))
import nov_navigation_recall_export as recall
import nov_navigation_memory_sync as nav
from nov_spatial_memory_sync import _observation_id

class RecallExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.world=self.root/"world.json"
        self.world.write_text('{"world_id":"fixture"}')
        self.private=self.root/"private.json"
        self.public=self.root/"public"/"recall.json"
    def envelope(self,kind="blocked_passage"):
        if kind=="blocked_passage":
            item={"kind":kind,"key":"0,0>1,0","from":[0,0],"to":[1,0],"observed_count":1}
        else:
            item={"kind":kind,"key":"5,0|0,0","from":[0,0],"to":[0,1],"goal":[5,0],"observed_count":1}
        request=nav.payload(item,"fixture","a"*64)
        return {**request,"observation_id":_observation_id(request["event"])}
    def run_export(self,items):
        return recall.export_once(self.world,self.private,self.public,fetch=lambda:{"semantic_projection":False,"items":items},now=lambda:1000.0)
    def test_only_api_retrieved_navigation_is_exported(self):
        self.assertEqual(self.run_export([self.envelope(),self.envelope("successful_route_step")])["cached"],2)
        private=json.loads(self.private.read_text())
        self.assertEqual(private,json.loads(self.public.read_text()))
        self.assertEqual(private["source"],"memoria.ia-local-structural-api")
        self.assertFalse(private["world_write_authority"])
        self.assertEqual(self.public.stat().st_mode & 0o777,0o644)
    def test_unrelated_hierarchy_ignored(self):
        row=self.envelope()
        row["provenance"]["hierarchy_id"]="different"
        self.assertEqual(self.run_export([row])["cached"],0)
    def test_bad_observation_identity_does_not_publish(self):
        row=self.envelope()
        row["observation_id"]="wrong"
        with self.assertRaises(nav.NavigationSyncError):
            self.run_export([row])
        self.assertFalse(self.public.exists())
    def test_cached_confirmed_records_survive_recent_window(self):
        self.run_export([self.envelope()])
        self.assertEqual(self.run_export([])["cached"],1)
    def test_failed_fetch_preserves_last_snapshot(self):
        self.run_export([self.envelope()])
        before=self.public.read_bytes()
        def unavailable():raise OSError("unavailable")
        with self.assertRaises(OSError):
            recall.export_once(self.world,self.private,self.public,fetch=unavailable)
        self.assertEqual(before,self.public.read_bytes())
    def test_world_change_discards_old_context(self):
        self.run_export([self.envelope()])
        self.world.write_text('{"world_id":"another"}')
        self.assertEqual(self.run_export([])["cached"],0)
    def test_changed_counter_keeps_latest_evidence(self):
        first=self.envelope()
        item=first["provenance"]["summary"].copy()
        item["observed_count"]=2
        request=nav.payload(item,"fixture","b"*64)
        newer={**request,"observation_id":_observation_id(request["event"])}
        self.run_export([first,newer])
        rows=json.loads(self.public.read_text())["entries"]
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]["observed_count"],2)
if __name__=="__main__":unittest.main()
