import unittest, tempfile, json, copy, math
from pathlib import Path
from world_weather_control import initial, process, publish, summary, validate_state, HORIZON_MS, HISTORY_LIMIT
from world_physical_weather import initial as physical_initial, advance, snapshot

class WeatherControlTest(unittest.TestCase):
    def observation(self, t, wind=1, humidity=0.5):
        return {"time_ms":t,"temperature_c":20,"humidity":humidity,
                "cloud_coverage":0.3,"wind_x_mps":wind,"wind_z_mps":0}

    def test_prediction_precedes_actual_future_and_does_not_use_it(self):
        state=process(initial("test",500),self.observation(0),"test",500,1000)
        trial=copy.deepcopy(state["pending"])
        state=process(state,self.observation(30000,7),"test",500,1030)
        self.assertEqual(state["pending"],trial)
        self.assertEqual(state["evaluated"],0)
        state=process(state,self.observation(60000,3),"test",500,1060)
        self.assertEqual(state["evaluated"],1)
        self.assertEqual(state["history"][0]["trial"],trial)
        self.assertEqual(state["absolute_error_sum"]["wind_x_mps"],2)
        self.assertEqual(summary(state,1060)["mean_wind_vector_error_mps"],2)
        self.assertEqual(state["pending"]["prediction"]["wind_x_mps"],3)
        self.assertEqual(state["pending"]["target_time_ms"],120000)

    def test_pause_and_duplicate_observations_do_not_create_trials(self):
        state=process(initial("test",500),self.observation(0),"test",500,1000)
        expected=copy.deepcopy(state)
        for now in range(1001,1011):
            state=process(state,self.observation(0),"test",500,now)
        self.assertEqual(state,expected)
        state=process(state,self.observation(60000),"test",500,1060)
        duplicate=process(state,self.observation(60000),"test",500,1061)
        self.assertEqual(state,duplicate)

    def test_late_window_missed_not_interpolated_or_backfilled(self):
        state=process(initial("test",500),self.observation(0),"test",500,1000)
        state=process(state,self.observation(66000,7),"test",500,1066)
        self.assertEqual(state["missed"],1)
        self.assertEqual(state["evaluated"],0)
        self.assertEqual(state["history"],[])
        self.assertEqual(state["pending"]["origin"]["time_ms"],66000)
        self.assertIsNone(summary(state,1066)["mean_wind_vector_error_mps"])
        self.assertIsNone(summary(state,1066)["mean_absolute_error"]["humidity"])

    def test_boundary_tolerance_is_accepted_with_actual_timestamp(self):
        state=process(initial("test",500),self.observation(0),"test",500,1000)
        state=process(state,self.observation(65000),"test",500,1065)
        self.assertEqual(state["evaluated"],1)
        self.assertEqual(state["history"][0]["observed"]["time_ms"],65000)

    def test_rewinds_identity_and_prediction_tampering_rejected(self):
        state=process(initial("test",500),self.observation(30000),"test",500,1000)
        for obs,world,duration,now in [(self.observation(0),"test",500,1001),
            (self.observation(31000),"other",500,1001),
            (self.observation(31000),"test",1000,1001),
            (self.observation(90000),"test",500,999)]:
            with self.assertRaises(ValueError):process(state,obs,world,duration,now)
        corrupt=copy.deepcopy(state);corrupt["pending"]["prediction"]["wind_x_mps"]=4
        with self.assertRaises(ValueError):process(corrupt,self.observation(90000),"test",500,1060)
        for bad in [True,float("nan"),float("inf"),9]:
            with self.assertRaises(ValueError):process(state,self.observation(31000,bad),"test",500,1001)

    def test_restart_modes_and_corruption_preserve_public_status(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);world=root/"world.json";weather=root/"weather.json";state=root/"control.json";public=root/"public.json"
            world.write_text('{"world_id":"test"}')
            physical=physical_initial({"world_id":"test","regions":[]},0,500)
            weather.write_text(json.dumps(snapshot(physical,1000)))
            args=dict(world=world,weather=weather,state=state,public=public,now=lambda:1000)
            publish(**args);trial=json.loads(state.read_text())["pending"]
            advance(physical,{"world_id":"test","regions":[]},60000)
            weather.write_text(json.dumps(snapshot(physical,1060)));args["now"]=lambda:1060
            publish(**args)
            saved=json.loads(state.read_text())
            self.assertEqual(saved["history"][0]["trial"],trial)
            self.assertEqual(saved["evaluated"],1)
            self.assertEqual(state.stat().st_mode&0o777,0o600)
            self.assertEqual(public.stat().st_mode&0o777,0o644)
            previous=public.read_bytes()
            saved["pending"]["prediction_id"]="broken";state.write_text(json.dumps(saved))
            with self.assertRaises(ValueError):publish(**args)
            self.assertEqual(public.read_bytes(),previous)

    def test_stale_or_wrong_world_observations_not_counted(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);world=root/"world";weather=root/"weather"
            world.write_text('{"world_id":"test"}')
            physical=physical_initial({"world_id":"test","regions":[]},0,500)
            weather.write_text(json.dumps(snapshot(physical,1000)))
            for now in [1181,900]:
                with self.assertRaises(ValueError):
                    publish(world,weather,root/"state",root/"public",now=lambda:now)
            self.assertFalse((root/"state").exists())
            world.write_text('{"world_id":"other"}')
            with self.assertRaises(ValueError):
                publish(world,weather,root/"state",root/"public",now=lambda:1000)

    def test_retention_bound_without_losing_cumulative_errors(self):
        state=initial("test",500)
        for i in range(HISTORY_LIMIT+4):
            state=process(state,self.observation(i*60000,1 if i%2 else 3),"test",500,1000+i*60)
        self.assertEqual(len(state["history"]),HISTORY_LIMIT)
        self.assertEqual(state["evaluated"],HISTORY_LIMIT+3)
        self.assertEqual(state["absolute_error_sum"]["wind_x_mps"],2*(HISTORY_LIMIT+3))
        self.assertEqual(summary(state,99999)["mean_absolute_error"]["wind_x_mps"],2)
        validate_state(state,"test",500)
