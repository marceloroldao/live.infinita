"""Bounded thermodynamic/wind simulation, independent of renderer FPS.
Not a numerical weather forecast or a claim of memory inference.
"""
import json,math,time
from hashlib import sha256
from pathlib import Path
from environmental_rules import _climate
from cognitive_terrain_projection import _read_json
from nov_navigation_memory_sync import write_checkpoint
from world_sky_clock import sky_clock
SCHEMA="live-infinita-physical-weather/v1"
WORLD=Path("/var/lib/live-infinita/autonomous-world/world.json")
CLOCK=WORLD.with_name("simulation-clock.json")
STATE=Path("/var/lib/live-infinita/weather/state.json")
OUTPUT=Path("/var/lib/live-infinita/cognitive-terrain/weather.json")
STEP_MS=1000
MAX_STEPS=600
PERIOD_M=4096.0

def saturation(t):
    # Approximate saturation mixing ratio in g/kg at 1013 hPa.
    e=6.112*math.exp(17.67*t/(t+243.5))
    return 622.0*e/(1013.0-e)

def clamp(x,a,b):return min(b,max(a,x))

def forcing(world):
    c=_climate(world)
    regions=world.get("regions",[])
    water=sum(isinstance(r,dict) and r.get("biome") in ["river","waterfall","lake"] for r in regions)
    return {"temperature":clamp(float(c["base_temperature_c"])+float(c["seasonal_temperature_offset_c"]),-10,38),
            "water_fraction":water/max(1,len(regions)),
            "humidity":0.82 if c["weather"] in ["rain","cloudy","storm"] else 0.65,
            "seed":int(sha256(world["world_id"].encode()).hexdigest()[:8],16)/4294967295.0*math.tau}

def initial(world,logical_ms,duration):
    f=forcing(world);t=f["temperature"]
    return {"schema":SCHEMA,"world_id":world["world_id"],"time_ms":logical_ms//STEP_MS*STEP_MS,
            "tick_duration_ms":duration,"temperature_c":t,"vapor_g_kg":clamp(saturation(t)*f["humidity"],0,35),
            "cloud_liquid_g_kg":0.08,"precipitated_g_kg":0.0,"wind_x_mps":2.0,"wind_z_mps":1.0,
            "cloud_offset_x_m":0.0,"cloud_offset_z_m":0.0}

def validate_state(s,world_id,duration):
    if type(duration) is not int or not 1<=duration<=60000:
        raise ValueError("weather_duration")
    if s.get("schema")!=SCHEMA or s.get("world_id")!=world_id or s.get("tick_duration_ms")!=duration:
        raise ValueError("weather_state_identity")
    if type(s.get("time_ms")) is not int or s["time_ms"]<0 or s["time_ms"]%STEP_MS:
        raise ValueError("weather_time")
    limits={"temperature_c":(-25,45),"vapor_g_kg":(0,35),"cloud_liquid_g_kg":(0,0.5),"precipitated_g_kg":(0,1e9),
            "wind_x_mps":(-8,8),"wind_z_mps":(-8,8),"cloud_offset_x_m":(0,PERIOD_M),"cloud_offset_z_m":(0,PERIOD_M)}
    for key,(low,high) in limits.items():
        v=s.get(key)
        if type(v) not in [int,float] or not math.isfinite(v) or not low<=v<=high:
            raise ValueError("weather_state_numeric")
    if math.hypot(s["wind_x_mps"],s["wind_z_mps"])>8.000001:
        raise ValueError("weather_wind_speed")
    return s

def step(s,f):
    dt=STEP_MS/1000.0;t=s["time_ms"]/1000.0
    sun=max(0.0,math.sin(math.tau*t/3600.0-math.pi/2))
    coverage=clamp(s["cloud_liquid_g_kg"]/0.25,0,1)
    target_t=clamp(f["temperature"]-4.0+8.0*sun-2.0*coverage,-25,45)
    s["temperature_c"]+=clamp((target_t-s["temperature_c"])*(1-math.exp(-dt/600.0)),-0.03*dt,0.03*dt)
    qs=saturation(s["temperature_c"])
    rh=clamp(s["vapor_g_kg"]/qs,0,1.2)
    evaporated=0.0015*(0.3+f["water_fraction"])*sun*max(0.0,1.0-rh)*dt
    condensed=max(0.0,s["vapor_g_kg"]-0.92*qs)*(1-math.exp(-dt/90.0))
    dissipated=min(s["cloud_liquid_g_kg"],s["cloud_liquid_g_kg"]*(0.0001+0.00025*sun+0.0008*max(0.0,1-rh))*dt)
    s["vapor_g_kg"]=clamp(s["vapor_g_kg"]+evaporated-condensed+dissipated,0,35)
    liquid=s["cloud_liquid_g_kg"]+condensed-dissipated
    s["precipitated_g_kg"]+=max(0.0,liquid-0.5)
    s["cloud_liquid_g_kg"]=clamp(liquid,0,0.5)
    seed=f["seed"]
    # Analytic bounded pressure-gradient forcing; inertial drag filters gusts.
    px=0.65*math.sin(t/310.0+seed)+0.25*math.cos(t/97.0+seed)+0.10*sun
    pz=0.65*math.cos(t/420.0+seed)+0.25*math.sin(t/137.0-seed)
    gx=0.35*math.sin(math.tau*t/17.0+seed)
    gz=0.25*math.sin(math.tau*t/37.0-seed)
    target_x=2.0+4.0*px+gx
    target_z=1.0+4.0*pz+gz
    blend=1-math.exp(-dt/45.0)
    s["wind_x_mps"]=clamp(s["wind_x_mps"]+(target_x-s["wind_x_mps"])*blend,-8,8)
    s["wind_z_mps"]=clamp(s["wind_z_mps"]+(target_z-s["wind_z_mps"])*blend,-8,8)
    speed=math.hypot(s["wind_x_mps"],s["wind_z_mps"])
    if speed>8:
        s["wind_x_mps"]*=8/speed;s["wind_z_mps"]*=8/speed
    s["cloud_offset_x_m"]=(s["cloud_offset_x_m"]+s["wind_x_mps"]*dt)%PERIOD_M
    s["cloud_offset_z_m"]=(s["cloud_offset_z_m"]+s["wind_z_mps"]*dt)%PERIOD_M
    s["time_ms"]+=STEP_MS

def advance(s,world,logical_ms,max_steps=MAX_STEPS):
    if type(logical_ms) is not int or logical_ms<s["time_ms"]:
        raise ValueError("weather_clock_rewind")
    if type(max_steps) is not int or not 1<=max_steps<=MAX_STEPS:
        raise ValueError("weather_step_budget")
    steps=min(max_steps,(logical_ms-s["time_ms"])//STEP_MS)
    f=forcing(world)
    for _ in range(steps):step(s,f)
    return steps

def snapshot(s,now):
    return {**s,"generated_at_unix":int(now),"source":"bounded_physical_simulation",
            "humidity":clamp(s["vapor_g_kg"]/saturation(s["temperature_c"]),0,1),
            "cloud_coverage":clamp(s["cloud_liquid_g_kg"]/0.25,0,1),
            "wind_speed_mps":math.hypot(s["wind_x_mps"],s["wind_z_mps"]),
            "fixed_step_ms":STEP_MS,"inference_influence":False,
            "world_write_authority":False,"selection_authority":False}

def publish(world=WORLD,clock=CLOCK,state=STATE,output=OUTPUT,now=time.time):
    w=_read_json(world,2*1024*1024,"weather_world");c=sky_clock(clock,w.get("world_id"))
    if c is None:raise ValueError("weather_clock_unavailable")
    if state.exists():
        s=validate_state(_read_json(state,8192,"weather_state"),w["world_id"],c["tick_duration_ms"])
    else:s=initial(w,c["logical_time_ms"],c["tick_duration_ms"])
    steps=advance(s,w,c["logical_time_ms"])
    validate_state(s,w["world_id"],c["tick_duration_ms"])
    write_checkpoint(state,s)
    value=snapshot(s,now())
    write_checkpoint(output,value,mode=0o644)
    return {"steps":steps,"time_ms":s["time_ms"],"wind_speed_mps":round(value["wind_speed_mps"],3),
            "cloud_coverage":round(value["cloud_coverage"],3),"inference_influence":False}

def read_weather(path,world_id,now=time.time):
    try:
        p=_read_json(path,8192,"weather")
        stamp=p.get("generated_at_unix")
        if p.get("source")!="bounded_physical_simulation" or p.get("inference_influence") is not False:return None
        validate_state(p,world_id,p.get("tick_duration_ms"))
        if type(stamp) is not int or not -30<=now()-stamp<=180:return None
        for key in ["humidity","cloud_coverage"]:
            if type(p.get(key)) not in [int,float] or not math.isfinite(p[key]) or not 0<=p[key]<=1:return None
        return p
    except (OSError,ValueError,TypeError,RuntimeError):return None

if __name__=="__main__":print(json.dumps(publish(),sort_keys=True))
