import copy
import json
import tempfile
import time
import unittest
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
import nov_animal_search_prediction as p
import nov_animal_memory_sync as bridge
from nov_spatial_memory_sync import _observation_id


def encounter(seq, stamp, x=1.0, z=1.0, duration=250, entity="test:rabbit:0"):
    return dict(sequence=seq, entity_id=entity, kind="rabbit",
                first_seen_ms=stamp, last_seen_ms=stamp+duration,
                first_observer_eye_m=[x,1.55,z-8], last_observer_eye_m=[x,1.55,z-8],
                first_target_m=[x,.55,z], last_target_m=[x,.55,z],
                sample_count=2, min_distance_m=65**.5, max_distance_m=65**.5,
                first_range_m=24, last_range_m=24, closed_reason="lost_visual_contact")


class PredictionTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source,self.ack,self.world,self.state,self.public = [self.root/n for n in ("source","ack","world","state","public")]
        self.world.write_text('{"world_id":"test"}')
        self.wall = time.time()
        self.session = "a"*32
        self.rows = [encounter(1,1000),encounter(2,40000),encounter(3,80000)]
        self.logical = 100000
        self.write_inputs()

    def tearDown(self):
        self.tmp.cleanup()

    def item(self,row):
        return {"encounter":row,
                "observation_id":_observation_id(bridge.payload("test",self.session,row)["event"]),
                "verified_at_unix":self.wall}

    def write_inputs(self):
        self.s = dict(schema=bridge.SCHEMA,world_id="test",session_id=self.session,
                      acknowledged_sequence=len(self.rows),next_sequence=len(self.rows)+1,
                      logical_time_ms=self.logical,generated_at_unix=self.wall,pending=[],
                      active={},dropped_samples=0,source="local_physics_eye_sensor",
                      contains_prediction=False,absence_claim=False,world_write_authority=False)
        self.source.write_text(json.dumps(p.sealed(self.s)))
        self.a = dict(schema=bridge.ACK_SCHEMA,world_id="test",session_id=self.session,
                      cursor=len(self.rows),last_observation_id=self.item(self.rows[-1])["observation_id"] if self.rows else None,
                      verified_history=[self.item(r) for r in self.rows][-16:])
        self.ack.write_text(json.dumps(bridge.seal_ack(self.a)))

    def run_prediction(self):
        return p.run_once(self.source,self.ack,self.world,self.state,self.public,self.wall)

    def add_future(self,stamp=110000,x=4,z=4):
        self.rows.append(encounter(len(self.rows)+1,stamp,x,z))
        self.logical=stamp+4000
        self.write_inputs()

    def test_three_independent_recalled_encounters_make_region_not_probability(self):
        result=self.run_prediction()
        self.assertEqual(result["reason"],"forecast_ready")
        forecast=result["forecasts"][0]
        self.assertEqual(forecast["center_xz_m"],[4,4])
        self.assertEqual(len(forecast["evidence_ids"]),3)
        self.assertEqual(forecast["expires_ms"]-forecast["issued_ms"],60000)
        self.assertFalse(result["decision_use"])
        self.assertFalse(result["score_is_probability"])
        self.assertFalse(result["world_write_authority"])
        self.assertTrue(result["contains_prediction"])

    def test_two_encounters_are_not_enough(self):
        self.rows=self.rows[:2];self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_continuous_window_splits_never_become_independent_visits(self):
        self.rows=[encounter(i+1,1000+29999*i,duration=29998) for i in range(5)]
        self.logical=160000;self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_same_pass_contact_flicker_is_not_recurrence(self):
        self.rows=[encounter(i+1,1000+10000*i) for i in range(8)]
        self.logical=100000;self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_sampling_more_frames_does_not_add_visits(self):
        self.rows=self.rows[:1];self.rows[0]["sample_count"]=200;self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_no_pooling_different_animals_or_cells(self):
        self.rows[1]=encounter(2,40000,entity="test:rabbit:1")
        self.rows[2]=encounter(3,80000,x=40)
        self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_stale_evidence_cannot_issue_forecast(self):
        self.logical=p.MAX_AGE_MS+100000;self.write_inputs()
        self.assertEqual(self.run_prediction()["forecasts"],[])

    def test_day_phase_wrap_is_continuous(self):
        rows=[self.item(encounter(i+1,1000+i*40000)) for i in range(3)]
        before=p.regions(rows,"test:rabbit:0",p.CYCLE_MS-p.HORIZON_MS-1)[0]["recurrence_score"]
        after=p.regions(rows,"test:rabbit:0",p.CYCLE_MS-p.HORIZON_MS+1)[0]["recurrence_score"]
        self.assertAlmostEqual(before,after,places=5)

    def test_future_sighting_evaluates_paired_before_any_new_forecast(self):
        initial=self.run_prediction();self.add_future()
        result=self.run_prediction()
        self.assertEqual(result["counters"]["paired"],1)
        evaluation=result["evaluations"][0]
        self.assertEqual(evaluation["forecast_id"],initial["forecasts"][0]["forecast_id"])
        self.assertLess(evaluation["issued_ms"],evaluation["observed_ms"])
        self.assertEqual(evaluation["memory_distance_m"],0)
        self.assertAlmostEqual(evaluation["last_seen_distance_m"],18**.5)
        self.assertEqual(result["paired_metrics"]["memory_hit_rate"],1)
        self.assertEqual(result["paired_metrics"]["last_seen_hit_rate"],1)
        self.assertFalse(result["learning_improvement_measured"])

    def test_other_animal_sighting_does_not_evaluate_forecast(self):
        self.run_prediction()
        self.rows.append(encounter(4,110000,entity="test:rabbit:1"))
        self.logical=114000;self.write_inputs()
        self.assertEqual(self.run_prediction()["counters"]["paired"],0)

    def test_delayed_ack_of_already_seen_encounter_is_not_future_evidence(self):
        self.run_prediction()
        self.rows.append(encounter(4,90000));self.logical=114000;self.write_inputs()
        result=self.run_prediction()
        self.assertEqual(result["counters"]["paired"],0)
        self.assertEqual(len(result["forecasts"]),1)

    def test_no_sighting_expires_without_counting_a_miss(self):
        self.run_prediction()
        self.logical=400001;self.write_inputs()
        result=self.run_prediction()
        self.assertEqual(result["counters"]["expired_without_observation"],1)
        self.assertEqual(result["counters"]["paired"],0)
        self.assertIsNone(result["paired_metrics"]["memory_hit_rate"])
        self.assertFalse(result["absence_claim"])

    def test_restart_and_same_tick_do_not_duplicate_forecast_or_evaluation(self):
        self.run_prediction()
        self.assertEqual(self.run_prediction()["counters"]["issued"],1)
        self.add_future();self.run_prediction()
        result=self.run_prediction()
        self.assertEqual(result["counters"]["paired"],1)
        self.assertEqual(result["counters"]["issued"],1)

    def test_corrupt_state_preserves_previous_file(self):
        self.run_prediction()
        self.state.write_text('{"payload":"{}","sha256":"wrong"}')
        before=self.state.read_bytes()
        with self.assertRaisesRegex(ValueError,"animal_search_state_checksum"):self.run_prediction()
        self.assertEqual(before,self.state.read_bytes())

    def test_forecast_geometry_tamper_even_with_resealed_state_is_rejected(self):
        self.run_prediction()
        state=json.loads(json.loads(self.state.read_text())["payload"])
        state["pending"][0]["center_xz_m"]=[100,100]
        self.state.write_text(json.dumps(p.sealed(state)))
        with self.assertRaisesRegex(ValueError,"animal_search_forecast_identity"):self.run_prediction()

    def test_rewind_world_and_session_switch_are_blocked(self):
        self.run_prediction()
        self.logical=99999;self.write_inputs()
        with self.assertRaisesRegex(ValueError,"animal_search_clock_rewind"):self.run_prediction()
        self.logical=100000;self.session="b"*32;self.write_inputs()
        with self.assertRaisesRegex(ValueError,"animal_search_state_identity"):self.run_prediction()
        self.world.write_text('{"world_id":"different"}')
        with self.assertRaises(ValueError):self.run_prediction()

    def test_unverified_or_forged_history_never_enters_predictor(self):
        self.a["verified_history"][0]["observation_id"]="structural-event:forged"
        self.ack.write_text(json.dumps(bridge.seal_ack(self.a)))
        with self.assertRaisesRegex(ValueError,"animal_search_history_identity"):self.run_prediction()
        self.assertFalse(self.state.exists())

    def test_stale_sensor_and_future_recalled_event_are_blocked(self):
        self.s["generated_at_unix"]=self.wall-181
        self.source.write_text(json.dumps(p.sealed(self.s)))
        with self.assertRaises(ValueError):self.run_prediction()
        self.write_inputs();self.s["logical_time_ms"]=50000
        self.source.write_text(json.dumps(p.sealed(self.s)))
        with self.assertRaisesRegex(ValueError,"animal_search_history_time_or_sequence"):self.run_prediction()

    def test_private_state_permissions_and_public_separate_prediction_flag(self):
        self.run_prediction()
        self.assertEqual(self.state.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.public.stat().st_mode & 0o777,0o644)
        self.assertNotIn("contains_prediction",json.loads(json.loads(self.source.read_text())["payload"])["pending"])

    def test_predictor_writes_only_separate_state_and_publication(self):
        original=p.write_checkpoint;writes=[]
        def track(path,value,mode=0o600):
            writes.append(path);original(path,value,mode)
        source_before=self.source.read_bytes();ack_before=self.ack.read_bytes()
        with patch.object(p,"write_checkpoint",side_effect=track):
            self.run_prediction()
        self.assertEqual(writes,[self.state,self.public])
        self.assertEqual(self.source.read_bytes(),source_before)
        self.assertEqual(self.ack.read_bytes(),ack_before)


    def test_real_frozen_structural_api_recall_feeds_forecast(self):
        import sys
        sys.path.insert(0,"/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src")
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
        service=ProductStructuralObservationService.open(self.root/"core",backend="sqlite",allow_fallback=False)
        app=FastAPI()
        key="isolated-search-test-key-"+"x"*32
        attach_structural_observation_routes(app,api_key=key,service=service)
        with TestClient(app) as client:
            def api(path,payload=None):
                response=client.post(path,json=payload,headers={"X-Memoria-Key":key}) if payload else client.get(path,headers={"X-Memoria-Key":key})
                self.assertEqual(response.status_code,201 if payload else 200)
                return response.json()
            self.s.update(acknowledged_sequence=0,pending=copy.deepcopy(self.rows))
            self.source.write_text(json.dumps(p.sealed(self.s)))
            self.ack.unlink()
            for i in range(3):
                result=bridge.sync_once(self.source,self.ack,self.root/"bridge-public",self.world,api)
                self.assertEqual(result["stored_and_recovered_encounters"],i+1)
            self.assertEqual(service.store.count,3)
            result=self.run_prediction()
            self.assertEqual(len(result["forecasts"]),1)
            self.assertEqual(len(result["forecasts"][0]["evidence_ids"]),3)
            self.assertFalse(result["decision_use"])


    def test_comparison_can_record_memory_win_and_memory_loss(self):
        for future_x, memory_hit, baseline_hit in [(4,True,False),(40,False,True)]:
            with self.subTest(future_x=future_x):
                if self.state.exists():self.state.unlink()
                self.rows=[encounter(1,1000),encounter(2,40000),encounter(3,80000),encounter(4,90000,x=40,z=4)]
                self.logical=100000;self.write_inputs()
                initial=self.run_prediction()
                self.assertEqual(initial["forecasts"][0]["last_seen_xz_m"],[40,4])
                self.add_future(x=future_x,z=4)
                result=self.run_prediction()
                self.assertEqual(result["counters"]["paired"],1)
                self.assertEqual(result["evaluations"][0]["memory_hit"],memory_hit)
                self.assertEqual(result["evaluations"][0]["last_seen_hit"],baseline_hit)


if __name__=="__main__":
    unittest.main()
