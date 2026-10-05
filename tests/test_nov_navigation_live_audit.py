import copy
import importlib.util
from pathlib import Path
import unittest
from test_nov_navigation_episode_sync import episode

spec=importlib.util.spec_from_file_location("live_audit",Path(__file__).resolve().parents[1]/"tools/audit_live_navigation_008cm.py")
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class LiveAuditTests(unittest.TestCase):
    def data(self,rows):
        return {"episodes":rows,"dropped_episodes":4}
    def test_agreement_is_not_causal_learning(self):
        row=episode();action=row["actions"][0]
        action["perception"]["without_memoria"]=action["selected"].copy()
        result=module.audit(self.data([row]))
        self.assertEqual(result["verified_causal_memoria"]["actions"],0)
        self.assertEqual(result["causal_claims_without_distinct_baseline"]["memoria"],1)
    def test_distinct_retrieved_step_and_completed_goal_are_separate(self):
        result=module.audit(self.data([episode()]))
        self.assertEqual(result["verified_causal_memoria"]["completed_steps"],1)
        self.assertEqual(result["verified_causal_memoria"]["goals_reached"],0)
        self.assertFalse(result["controlled_live_gain_measured"])
    def test_ram_interruption_not_counted_as_success(self):
        row=episode();action=row["actions"][0]
        action.update(decision_source="working-memory",memory_observation_id="",outcome="interrupted",
            working_memory_changed_choice=True,working_memory_key="5,0|0,0",reason="new_decision")
        action["perception"]["without_working_memory"]=[1.0,0.0]
        result=module.audit(self.data([row]))
        self.assertEqual(result["verified_causal_ram"]["actions"],1)
        self.assertEqual(result["verified_causal_ram"]["completed_steps"],0)
        self.assertEqual(result["verified_causal_memoria"]["actions"],0)
    def test_duplicate_snapshot_evidence_not_counted_twice(self):
        result=module.audit(self.data([episode(),copy.deepcopy(episode())]))
        self.assertEqual(result["all"]["actions"],1)
        self.assertEqual(result["duplicate_actions_ignored"],1)
    def test_conflicting_action_identity_rejected(self):
        changed=episode();changed["actions"][0]["end"]=[0,2]
        with self.assertRaisesRegex(ValueError,"identity_changed"):
            module.audit(self.data([episode(),changed]))
    def test_empty_window_keeps_unknown_times(self):
        result=module.audit(self.data([]))
        self.assertIsNone(result["window_started_at_unix"])
        self.assertEqual(result["all"]["actions"],0)


class CommittedRouteAuditTests(unittest.TestCase):
    def action(self,serial=1,world="fixture",goal=(5.0,0.0),outcome="step_reached"):
        row=episode()
        action=row["actions"][0]
        action.update(route_goal_id="c"*32+":1",decision_serial=serial,goal=list(goal),outcome=outcome)
        action["context_start"]["world_id"]=world
        action["context_end"]["world_id"]=world
        return action
    def test_goal_observation_does_not_claim_full_coverage(self):
        result=module.route_metrics([self.action(),self.action(2,outcome="goal_reached")])
        route=result["routes"][0]
        self.assertTrue(route["goal_reached_observed"])
        self.assertFalse(route["full_route_coverage_proven"])
        self.assertEqual(route["observed"]["actions"],2)
        self.assertEqual(route["causal_memoria_actions"],2)
    def test_worlds_are_not_conflated(self):
        result=module.route_metrics([self.action(world="a"),self.action(world="b")])
        self.assertEqual(len(result["routes"]),2)
    def test_goal_drift_is_disclosed(self):
        route=module.route_metrics([self.action(),self.action(2,goal=(10,0))])["routes"][0]
        self.assertFalse(route["goal_consistent"])
        self.assertIsNone(route["goal"])
    def test_older_actions_remain_counted_without_route_identity(self):
        result=module.route_metrics([episode()["actions"][0]])
        self.assertEqual(result["actions_without_route_identity"],1)
        self.assertEqual(result["routes"],[])


class SessionAndPathAuditTests(unittest.TestCase):
    def data(self):
        old=episode()
        old["actions"][0]["outcome"]="goal_reached"
        new=episode(2)
        new["session_id"]="d"*32
        new["actions"][0].update(started_at_unix=200.0,ended_at_unix=201.0)
        return {"episodes":[new,old],"dropped_episodes":4}
    def test_latest_session_is_selected_by_time_not_archive_order(self):
        data=self.data()
        result=module.audit(data,latest_session=True)
        self.assertEqual(result["selected_session_id"],"d"*32)
        self.assertEqual(result["all"]["actions"],1)
        self.assertEqual(result["all"]["goals_reached"],0)
        self.assertEqual(result["source_retention_dropped"],4)
        self.assertNotIn("_audit_session_id",data["episodes"][0]["actions"][0])
    def test_explicit_and_missing_session(self):
        self.assertEqual(module.audit(self.data(),session="b"*32)["all"]["goals_reached"],1)
        with self.assertRaisesRegex(ValueError,"absent"):
            module.audit(self.data(),session="absent")
        with self.assertRaisesRegex(ValueError,"either"):
            module.audit(self.data(),session="b"*32,latest_session=True)
    def test_same_route_identity_in_two_sessions_is_not_combined(self):
        data=self.data()
        for row in data["episodes"]:
            row["actions"][0]["route_goal_id"]="c"*32+":1"
        result=module.audit(data)
        self.assertEqual(len(result["committed_routes"]["routes"]),2)
    def test_empty_latest_session_is_a_valid_empty_window(self):
        result=module.audit({"episodes":[],"dropped_episodes":0},latest_session=True)
        self.assertEqual(result["all"]["actions"],0)
        self.assertIsNone(result["selected_session_id"])
    def test_distance_and_revisited_passages(self):
        rows=[]
        for serial,(start,end) in enumerate([([0,0],[1,0]),([1,0],[0,0]),([0,0],[1,0])]):
            row=episode()["actions"][0]
            row.update(start=start,end=end,decision_serial=serial+1,started_at_unix=100+serial,
                ended_at_unix=101+serial,route_goal_id="c"*32+":1")
            rows.append(row)
        route=module.route_metrics(rows)["routes"][0]
        quality=route["path_quality"]
        self.assertEqual(route["observed"]["observed_distance_m"],3)
        self.assertEqual(quality["repeated_directed_passage_actions"],1)
        self.assertEqual(quality["net_goal_approach_m"],1)
        self.assertAlmostEqual(quality["goal_approach_per_observed_m"],1/3)
        self.assertFalse(quality["shortest_route_proven"])
        self.assertFalse(route["full_route_coverage_proven"])
    def test_gap_or_changed_goal_cannot_claim_path_ratio(self):
        a=episode()["actions"][0]
        b=copy.deepcopy(a)
        b.update(start=[10,0],end=[11,0])
        self.assertIsNone(module.path_quality([a,b],True)["goal_approach_per_observed_m"])
        self.assertIsNone(module.path_quality([a,b],False)["net_goal_approach_m"])
    def test_detour_can_have_negative_goal_approach(self):
        a=episode()["actions"][0]
        a.update(start=[0,0],end=[-1,0])
        q=module.path_quality([a],True)
        self.assertEqual(q["net_goal_approach_m"],-1)
        self.assertEqual(q["repeated_directed_passage_actions"],0)
    def test_only_completed_shortcut_steps_count(self):
        a=episode()["actions"][0]
        a["perception"]["observed_route_shortcut_waypoints"]=2
        b=copy.deepcopy(a)
        b["outcome"]="no_passage_sensed"
        self.assertEqual(module.metrics([a,b])["completed_shortcut_steps"],1)
