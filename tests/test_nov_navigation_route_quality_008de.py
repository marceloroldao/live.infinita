import importlib.util
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location("route_quality_benchmark",ROOT/"tools/benchmark_navigation_route_quality_008de.py")
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class RouteQualityLearningTests(unittest.TestCase):
    def action(self,start,end,selected=None,outcome="step_reached",serial=1):
        return {"start":start,"end":end,"selected":selected or end,"goal":[3,0],
            "outcome":outcome,"decision_serial":serial}
    def episode(self,actions,reached=True,collisions=0):
        return {"actions":actions,"reached":reached,"collisions":collisions}

    def test_cost_comes_from_executed_segments_and_entire_remaining_episode(self):
        actions=[self.action([0,0],[1,0],[100,0]),
            self.action([1,0],[1,2],serial=2),
            self.action([1,2],[3,0],outcome="goal_reached",serial=3)]
        quality,evidence=module.learn_route_quality([self.episode(actions)])
        self.assertAlmostEqual(quality["3,0|0,0@2000,0"]["remaining_cost_m"],3+8**0.5)
        self.assertEqual(len(evidence),3)

    def test_same_address_compares_only_observed_alternative_choices(self):
        longer=self.episode([self.action([0,0],[0,1]),
            self.action([0,1],[3,0],outcome="goal_reached",serial=2)])
        shorter=self.episode([self.action([0,0],[1,0]),
            self.action([1,0],[3,0],outcome="goal_reached",serial=2)])
        quality,_=module.learn_route_quality([longer,shorter])
        bad=quality["3,0|0,0@0,20"]
        good=quality["3,0|0,0@20,0"]
        self.assertEqual(bad["reference_cost_m"],3.0)
        self.assertGreater(bad["remaining_cost_m"],good["remaining_cost_m"])
        self.assertEqual(good["remaining_cost_m"],good["reference_cost_m"])

    def test_failed_incomplete_or_colliding_episodes_are_not_success_costs(self):
        step=self.action([0,0],[1,0])
        goal=self.action([1,0],[3,0],outcome="goal_reached")
        rows=[self.episode([step],reached=False),self.episode([step]),
            self.episode([step,goal],collisions=1),
            self.episode([self.action([0,0],[0,0],outcome="blocked"),goal])]
        self.assertEqual(module.learn_route_quality(rows),({},[]))

    def test_observations_are_averaged_without_inventing_untried_actions(self):
        row=self.episode([self.action([0,0],[3,0],outcome="goal_reached")])
        quality,_=module.learn_route_quality([row,row])
        self.assertEqual(list(quality),["3,0|0,0@60,0"])
        self.assertEqual(quality["3,0|0,0@60,0"]["samples"],2)
        self.assertEqual(quality["3,0|0,0@60,0"]["remaining_cost_m"],3.0)

    def test_quantization_matches_godot_negative_half_rounding(self):
        self.assertEqual(module.quality_key("a",[-0.025,0.025]),"a@-1,1")

    def test_candidate_scoring_is_production_code_except_quality_and_evidence(self):
        production=(ROOT/"apps/renderer-godot/nov_navigation_experience.gd").read_text()
        expected=production[production.index("func _anticipated_target("):production.index("\n\n# Shortcuts")]
        actual=(ROOT/"tests/nov_trial_error_quality_008de.gd").read_text()
        actual=actual[actual.index("func _anticipated_target("):].rstrip()
        actual=actual.replace("quality_bonus(address,next,1.5)","1.5").replace("quality_bonus(address,next,2.0)","2.0")
        actual=actual.replace(',"memory_bonus":candidate["bonus"]','')
        actual=actual.replace('    decision_evidence["selected_memory_bonus"] = chosen["bonus"]\n','')
        actual=actual.replace('    decision_evidence["route_quality_enabled"] = quality_enabled\n','')
        self.assertEqual(actual,expected.rstrip())
