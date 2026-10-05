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
        self.status={"schema":"live-infinita-nov-learning-status/v1","world_id":"fixture",
                     "observed_at_unix":998,"arrivals":0,"interruptions":0,"blocked_attempts":0,
                     "completed_steps":27,"causal_ram_steps":3,"causal_memoria_steps":1,
                     "distance_m":26.5,"active":True,"motion_state":"walking"}
        self.source.write_text(json.dumps(self.status))
    def export(self):
        return panel.export_once(self.world,self.source,self.public,now=lambda:1000)
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
