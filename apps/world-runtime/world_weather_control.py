"""Prospective weather persistence control; no memory or physics authority.

Commit a prediction before observing its future outcome. Skipped target windows
are missed trials, never interpolated observations or retroactive predictions.
"""
from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path
import time
from cognitive_terrain_projection import _read_json, _canonical
from nov_navigation_memory_sync import write_checkpoint
from world_physical_weather import read_weather, WORLD, OUTPUT as WEATHER

SCHEMA = "live-infinita-weather-control/v1"
STATE = Path("/var/lib/live-infinita/weather/control.json")
PUBLIC = Path("/var/www/live-infinita-godot/navigation-memory/weather-control.json")
HORIZON_MS = 60000
TOLERANCE_MS = 5000
HISTORY_LIMIT = 512
FIELDS = {"temperature_c": (-25, 45), "humidity": (0, 1),
          "cloud_coverage": (0, 1), "wind_x_mps": (-8, 8), "wind_z_mps": (-8, 8)}


def sample(value):
    result = {"time_ms": value["time_ms"], "values": {k: value[k] for k in FIELDS}}
    validate_sample(result)
    return result


def validate_sample(s):
    if not isinstance(s, dict) or type(s.get("time_ms")) is not int or s["time_ms"] < 0:
        raise ValueError("control_sample_time")
    values = s.get("values")
    if not isinstance(values, dict) or set(values) != set(FIELDS):
        raise ValueError("control_sample_fields")
    for k, (low, high) in FIELDS.items():
        v = values[k]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError("control_sample_numeric")
    if math.hypot(values["wind_x_mps"], values["wind_z_mps"]) > 8.000001:
        raise ValueError("control_sample_wind")


def trial_id(trial):
    return sha256(_canonical({k: v for k, v in trial.items() if k != "prediction_id"})).hexdigest()


def issue(s, world_id, duration, now):
    trial = {"method": "persistence_control", "world_id": world_id,
             "tick_duration_ms": duration, "issued_at_unix": now,
             "origin": deepcopy(s), "target_time_ms": s["time_ms"] + HORIZON_MS,
             "prediction": deepcopy(s["values"]), "memory_used": False}
    trial["prediction_id"] = trial_id(trial)
    return trial


def validate_trial(t, world_id, duration):
    if not isinstance(t, dict) or t.get("method") != "persistence_control" or t.get("world_id") != world_id or t.get("tick_duration_ms") != duration or t.get("memory_used") is not False:
        raise ValueError("control_trial_identity")
    validate_sample(t.get("origin"))
    if t.get("target_time_ms") != t["origin"]["time_ms"] + HORIZON_MS or t.get("prediction") != t["origin"]["values"]:
        raise ValueError("control_trial_prediction")
    stamp = t.get("issued_at_unix")
    if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError("control_trial_stamp")
    if t.get("prediction_id") != trial_id(t):
        raise ValueError("control_trial_digest")


def initial(world_id, duration):
    return {"schema": SCHEMA, "world_id": world_id, "tick_duration_ms": duration,
            "last_time_ms": None, "pending": None, "evaluated": 0, "missed": 0,
            "absolute_error_sum": {k: 0.0 for k in FIELDS}, "wind_vector_error_sum_mps": 0.0,
            "history": []}


def validate_state(s, world_id, duration):
    if type(duration) is not int or not 1 <= duration <= 60000 or not isinstance(s, dict) or s.get("schema") != SCHEMA or s.get("world_id") != world_id or s.get("tick_duration_ms") != duration:
        raise ValueError("control_state_identity")
    last = s.get("last_time_ms")
    if last is not None and (type(last) is not int or last < 0):
        raise ValueError("control_state_time")
    for k in ("evaluated", "missed"):
        if type(s.get(k)) is not int or not 0 <= s[k] <= 1000000000:
            raise ValueError("control_counter")
    sums = s.get("absolute_error_sum")
    if not isinstance(sums, dict) or set(sums) != set(FIELDS):
        raise ValueError("control_error_fields")
    for v in [*sums.values(), s.get("wind_vector_error_sum_mps")]:
        if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1e12:
            raise ValueError("control_error_sum")
    pending = s.get("pending")
    if pending is not None:
        validate_trial(pending, world_id, duration)
        if last is None or not pending["origin"]["time_ms"] <= last < pending["target_time_ms"]:
            raise ValueError("control_pending_time")
    history = s.get("history")
    if not isinstance(history, list) or len(history) > HISTORY_LIMIT:
        raise ValueError("control_history_limit")
    previous = -1
    for row in history:
        validate_trial(row.get("trial"), world_id, duration)
        observed = row.get("observed")
        validate_sample(observed)
        t = row["trial"]
        if not t["target_time_ms"] <= observed["time_ms"] <= t["target_time_ms"] + TOLERANCE_MS or t["origin"]["time_ms"] < previous:
            raise ValueError("control_history_time")
        previous = observed["time_ms"]
        if last is None or observed["time_ms"] > last:
            raise ValueError("control_history_future")
    return s


def process(s, observation, world_id, duration, now):
    validate_state(s, world_id, duration)
    current = sample(observation)
    if s["last_time_ms"] is not None and current["time_ms"] < s["last_time_ms"]:
        raise ValueError("control_clock_rewind")
    state = deepcopy(s)
    pending = state["pending"]
    if pending is not None and current["time_ms"] >= pending["target_time_ms"]:
        if current["time_ms"] <= pending["target_time_ms"] + TOLERANCE_MS:
            if now < pending["issued_at_unix"]:
                raise ValueError("control_wall_clock_rewind")
            errors = {k: abs(current["values"][k] - pending["prediction"][k]) for k in FIELDS}
            for k, error in errors.items(): state["absolute_error_sum"][k] += error
            state["wind_vector_error_sum_mps"] += math.hypot(errors["wind_x_mps"], errors["wind_z_mps"])
            state["evaluated"] += 1
            state["history"].append({"trial": pending, "observed": current})
            state["history"] = state["history"][-HISTORY_LIMIT:]
        else:
            state["missed"] += 1
        state["pending"] = None
    if state["pending"] is None:
        state["pending"] = issue(current, world_id, duration, now)
    state["last_time_ms"] = current["time_ms"]
    validate_state(state, world_id, duration)
    return state


def summary(s, now):
    count = s["evaluated"]
    return {"schema": SCHEMA, "world_id": s["world_id"], "generated_at_unix": now,
            "source": "prospective_physical_weather_control", "method": "persistence_control",
            "horizon_ms": HORIZON_MS, "late_tolerance_ms": TOLERANCE_MS,
            "evaluated": count, "missed": s["missed"], "last_time_ms": s["last_time_ms"],
            "mean_absolute_error": {k: v / count if count else None for k, v in s["absolute_error_sum"].items()},
            "mean_wind_vector_error_mps": s["wind_vector_error_sum_mps"] / count if count else None,
            "pending": s["pending"], "last_evaluation": s["history"][-1] if s["history"] else None,
            "retained_evaluations": len(s["history"]), "memory_used": False,
            "nov_prediction": False, "inference_influence": False, "world_write_authority": False}


def publish(world=WORLD, weather=WEATHER, state=STATE, public=PUBLIC, now=time.time):
    world_id = _read_json(world, 2*1024*1024, "control_world").get("world_id")
    stamp = now()
    observation = read_weather(weather, world_id, now=lambda: stamp)
    if observation is None: raise ValueError("control_weather_unavailable")
    duration = observation["tick_duration_ms"]
    s = _read_json(state, 2*1024*1024, "control_state") if state.exists() else initial(world_id, duration)
    result = process(s, observation, world_id, duration, stamp)
    # Durable prediction always precedes public status; future runs evaluate it.
    write_checkpoint(state, result)
    write_checkpoint(public, summary(result, stamp), mode=0o644)
    return {"evaluated": result["evaluated"], "missed": result["missed"],
            "pending_target_time_ms": result["pending"]["target_time_ms"], "memory_used": False}


if __name__ == "__main__": print(json.dumps(publish(), sort_keys=True))
