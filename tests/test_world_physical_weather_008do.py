import unittest,copy,json,math,tempfile
from pathlib import Path
from world_physical_weather import initial,advance,forcing,step,validate_state,publish,read_weather,SCHEMA

class WeatherTest(unittest.TestCase):
    def setUp(self):
        self.world={"world_id":"test","regions":[{"biome":"forest"},{"biome":"river"}],"environment":{}}
    def test_fixed_timestep_partition_is_identical(self):
        a=initial(self.world,0,500);b=copy.deepcopy(a)
        advance(a,self.world,300000)
        for t in [33000,99000,175000,300000]:advance(b,self.world,t)
        self.assertEqual(a,b)
    def test_clock_pause_restart_and_publication(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);world=d/"world.json";clock=d/"clock.json";state=d/"state.json";output=d/"weather.json"
            world.write_text(json.dumps(self.world))
            c={"clock_schema":"simulation_clock_v1","tick":0,"tick_duration_ms":500,"paused":False};clock.write_text(json.dumps(c))
            kwargs=dict(world=world,clock=clock,state=state,output=output,now=lambda:1000)
            publish(**kwargs);c["tick"]=120;clock.write_text(json.dumps(c))
            publish(**kwargs);saved=json.loads(state.read_text())
            expected=initial(self.world,0,500);advance(expected,self.world,60000)
            self.assertEqual(saved,expected)
            c["paused"]=True;clock.write_text(json.dumps(c));publish(**kwargs)
            self.assertEqual(saved,json.loads(state.read_text()))
            self.assertIsNotNone(read_weather(output,"test",now=lambda:1000))
            self.assertIsNone(read_weather(output,"other",now=lambda:1000))
            self.assertIsNone(read_weather(output,"test",now=lambda:1181))
            self.assertEqual(output.stat().st_mode & 0o777,0o644)
            self.assertEqual(state.stat().st_mode & 0o777,0o600)
    def test_condensation_conserves_water_including_fallout(self):
        s=initial(self.world,0,500);s["vapor_g_kg"]=30;s["cloud_liquid_g_kg"]=0.48
        before=s["vapor_g_kg"]+s["cloud_liquid_g_kg"]+s["precipitated_g_kg"]
        step(s,forcing(self.world))
        after=s["vapor_g_kg"]+s["cloud_liquid_g_kg"]+s["precipitated_g_kg"]
        self.assertAlmostEqual(before,after,places=10)
        self.assertGreater(s["precipitated_g_kg"],0)
    def test_dry_air_dissipates_cloud(self):
        s=initial(self.world,1800000,500);s["vapor_g_kg"]=0.1;s["cloud_liquid_g_kg"]=0.2
        step(s,forcing(self.world))
        self.assertLess(s["cloud_liquid_g_kg"],0.2)
        self.assertGreater(s["vapor_g_kg"],0.1)
    def test_cloud_displacement_uses_actual_wind(self):
        s=initial(self.world,0,500);step(s,forcing(self.world))
        self.assertAlmostEqual(s["cloud_offset_x_m"],s["wind_x_mps"]%4096,places=10)
        self.assertAlmostEqual(s["cloud_offset_z_m"],s["wind_z_mps"]%4096,places=10)
    def test_long_cycle_bounds_variation_and_step_budget(self):
        s=initial(self.world,0,500);winds=[];temps=[]
        for t in range(600000,3600001,600000):
            advance(s,self.world,t);validate_state(s,"test",500)
            winds.append((s["wind_x_mps"],s["wind_z_mps"]));temps.append(s["temperature_c"])
            self.assertLessEqual(math.hypot(*winds[-1]),8.000001)
        self.assertGreater(max(temps)-min(temps),1)
        self.assertGreater(max(w[0] for w in winds)-min(w[0] for w in winds),1)
        self.assertEqual(advance(s,self.world,10000000),600)
        with self.assertRaises(ValueError):advance(s,self.world,0)
    def test_corrupt_input_preserves_previous_output(self):
        with tempfile.TemporaryDirectory() as d:
            d=Path(d);world=d/"world.json";clock=d/"clock.json";state=d/"state.json";output=d/"weather.json"
            world.write_text(json.dumps(self.world));clock.write_text(json.dumps({"clock_schema":"simulation_clock_v1","tick":0,"tick_duration_ms":500,"paused":False}))
            kwargs=dict(world=world,clock=clock,state=state,output=output,now=lambda:1000)
            publish(**kwargs);previous=output.read_bytes()
            s=json.loads(state.read_text());s["wind_x_mps"]=float("nan");state.write_text(json.dumps(s))
            with self.assertRaises(ValueError):publish(**kwargs)
            self.assertEqual(previous,output.read_bytes())
    def test_extreme_climate_initial_state_is_bounded(self):
        world={**self.world,"environment":{"weather":"rain","climate":{"base_temperature_c":38,"seasonal_temperature_offset_c":15}}}
        s=initial(world,0,500);validate_state(s,"test",500)
        for key,bad in [("tick_duration_ms",True),("temperature_c",True),("wind_x_mps",9),("cloud_liquid_g_kg",-1)]:
            row={**s,key:bad}
            with self.assertRaises(ValueError):validate_state(row,"test",row["tick_duration_ms"])
