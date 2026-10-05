import json
from pathlib import Path
import tempfile
import unittest
from nov_navigation_recall_export import read_learning_status,export_once

class LearningPanelTests(unittest.TestCase):
    def status(self):
        return {"schema":"live-infinita-nov-learning-status/v1","world_id":"fixture","observed_at_unix":100.0,
            "arrivals":2,"interruptions":1,"blocked_attempts":0,"completed_steps":20,
            "causal_ram_steps":3,"causal_memoria_steps":0,"result":"chegou: 12.0 m"}
    def test_fresh_native_counts_are_exported_in_recall_without_learning_claim(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/"world.json").write_text(json.dumps({"world_id":"fixture"}))
            (root/"panel.json").write_text(json.dumps(self.status()))
            export_once(root/"world.json",root/"private.json",root/"public.json",
                fetch=lambda:{"semantic_projection":False,"items":[]},now=lambda:110,
                panel_source=root/"panel.json")
            result=json.loads((root/"public.json").read_text())
            self.assertEqual(result["learning_status"]["arrivals"],2)
            self.assertEqual(result["learning_status"]["source"],"native_renderer_journey")
            self.assertNotIn("improvement",result["learning_status"])
            self.assertEqual(result["entries"],[])
    def test_stale_future_or_other_world_counts_are_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"panel.json"
            path.write_text(json.dumps(self.status()))
            self.assertIsNone(read_learning_status(path,"fixture",161))
            self.assertIsNone(read_learning_status(path,"fixture",99))
            self.assertIsNone(read_learning_status(path,"other",110))
    def test_invalid_counters_and_symlink_cannot_supply_a_panel(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"panel.json"
            for invalid in [-1,1.5,True,"2"]:
                value=self.status();value["arrivals"]=invalid
                path.write_text(json.dumps(value))
                self.assertIsNone(read_learning_status(path,"fixture",110))
            path.write_text(json.dumps(self.status()))
            link=Path(directory)/"link.json";link.symlink_to(path)
            self.assertIsNone(read_learning_status(link,"fixture",110))
    def test_json_integral_float_counters_are_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"panel.json"
            value=self.status();value["arrivals"]=2.0
            path.write_text(json.dumps(value))
            self.assertEqual(read_learning_status(path,"fixture",110)["arrivals"],2)

    def test_current_distance_and_active_state_survive_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"panel.json"
            value=self.status();value["distance_m"]=12.5;value["active"]=True
            path.write_text(json.dumps(value))
            result=read_learning_status(path,"fixture",110)
            self.assertEqual(result["distance_m"],12.5)
            self.assertIs(result["active"],True)
            for bad in [-1,float("nan"),float("inf"),True,"12"]:
                value["distance_m"]=bad
                path.write_text(json.dumps(value))
                self.assertIsNone(read_learning_status(path,"fixture",110))

    def test_blocked_and_egress_states_reach_panel_without_fake_counters(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"panel.json"
            value=self.status();value["active"]=True;value["distance_m"]=0.0
            for state in ("no_passage","water_egress"):
                value["motion_state"]=state;value["last_reason"]="cognitive_lake"
                path.write_text(json.dumps(value))
                result=read_learning_status(path,"fixture",110)
                self.assertEqual(result["motion_state"],state)
                self.assertEqual(result["last_reason"],"cognitive_lake")
                self.assertEqual(result["arrivals"],2)
            value["motion_state"]="invented"
            path.write_text(json.dumps(value))
            self.assertIsNone(read_learning_status(path,"fixture",110))
