import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import nov_navigation_panel_export as panel

class PanelDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.world=self.root/"world.json"
        self.world.write_text('{"world_id":"fixture"}')
        self.source=self.root/"native.json"
        self.public=self.root/"public/status.json"
        self.recall=self.root/"recall.json"
        self.status={"schema":"live-infinita-nov-learning-status/v1","world_id":"fixture",
                     "observed_at_unix":998,"arrivals":0,"interruptions":0,"blocked_attempts":0,
                     "completed_steps":27,"causal_ram_steps":3,"causal_memoria_steps":1,
                     "distance_m":26.5,"active":True,"motion_state":"walking"}
        self.source.write_text(json.dumps(self.status))
    def export(self):
        return panel.export_once(self.world,self.source,self.public,now=lambda:1000,recall=self.recall)
    def test_fresh_counters_publish_without_memory_api(self):
        with patch("nov_navigation_recall_export.fetch_recent",side_effect=OSError("offline")):
            self.assertTrue(self.export()["available"])
        d=json.loads(self.public.read_text())
        self.assertEqual(d["learning_status"]["completed_steps"],27)
        self.assertEqual(d["learning_status"]["causal_memoria_steps"],1)
        self.assertEqual(self.public.stat().st_mode & 0o777,0o644)
    def test_stale_source_clears_status_without_fabricating_zeros(self):
        self.export()
        self.status["observed_at_unix"]=900
        self.source.write_text(json.dumps(self.status))
        self.assertFalse(self.export()["available"])
        self.assertEqual(json.loads(self.public.read_text())["learning_status"],{})
    def test_replacement_already_has_public_permissions(self):
        import os
        real_replace = os.replace
        modes = []
        def replace(source, target):
            modes.append(Path(source).stat().st_mode & 0o777)
            real_replace(source, target)
        with patch("nov_navigation_panel_export.os.replace", side_effect=replace):
            self.export()
        self.assertEqual(modes, [0o644])
    def test_interrupted_preparation_preserves_previous_public_file(self):
        self.export()
        before = self.public.read_bytes()
        with patch("nov_navigation_panel_export.os.fsync", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError):
                self.export()
        self.assertEqual(self.public.read_bytes(), before)
        self.assertEqual(self.public.stat().st_mode & 0o777,0o644)
        self.assertEqual(list(self.public.parent.glob("status.json.*")), [])

    def make_recall(self, stamp=999, world="fixture"):
        self.recall.write_text(json.dumps({"schema":panel.RECALL_SCHEMA,"world_id":world,
            "source":"memoria.ia-local-structural-api","generated_at_unix":stamp,
            "entries":[{"kind":"successful_route_step","observation_id":"structural-event:"+"a"*40,
                        "route_quality":{"samples":1,"remaining_cost_m":8,"reference_cost_m":8}},
                       {"kind":"successful_route_step","observation_id":"structural-event:"+"b"*40},
                       {"kind":"blocked_passage","observation_id":"structural-event:"+"c"*40}]}))
    def test_server_recall_counts_are_separate_from_causal_choices(self):
        self.make_recall()
        self.export()
        d=json.loads(self.public.read_text())
        self.assertEqual(d["memoria_recall"]["routes"],2)
        self.assertEqual(d["memoria_recall"]["with_cost"],1)
        self.assertEqual(d["learning_status"]["causal_memoria_steps"],1)
    def test_stale_or_other_world_recall_is_unavailable(self):
        for stamp,world in [(700,"fixture"),(999,"other")]:
            self.make_recall(stamp,world)
            self.export()
            self.assertEqual(json.loads(self.public.read_text())["memoria_recall"],{"available":False})
    def test_invalid_cost_does_not_count_as_evaluated_route(self):
        self.make_recall()
        d=json.loads(self.recall.read_text())
        d["entries"][0]["route_quality"]["samples"]=True
        self.recall.write_text(json.dumps(d))
        self.export()
        self.assertEqual(json.loads(self.public.read_text())["memoria_recall"]["with_cost"],0)

    def test_recovery_count_is_carried_without_faking_arrivals(self):
        self.status["recoveries"]=2
        self.source.write_text(json.dumps(self.status))
        self.export()
        d=json.loads(self.public.read_text())["learning_status"]
        self.assertEqual(d["recoveries"],2)
        self.assertEqual(d["arrivals"],0)
        self.status["recoveries"]=True
        self.source.write_text(json.dumps(self.status))
        self.assertFalse(self.export()["available"])

    def test_wrong_world_rejected(self):
        self.world.write_text('{"world_id":"other"}')
        self.assertFalse(self.export()["available"])
    def test_new_native_progress_replaces_prior_counters(self):
        self.export()
        self.status["completed_steps"]=32
        self.source.write_text(json.dumps(self.status))
        self.export()
        self.assertEqual(json.loads(self.public.read_text())["learning_status"]["completed_steps"],32)

if __name__=="__main__":unittest.main()
