"""Prospective paired weather recall experiment on the frozen structural API.

Memoria.ia stores/returns measured transitions. The application's bounded analog
predictor uses those retrieved records; it never calls the physical step model.
"""
from copy import deepcopy
from hashlib import blake2b, sha256
import json
import math
import os
from pathlib import Path
import time
from urllib.request import Request, ProxyHandler, build_opener
from cognitive_terrain_projection import _read_json, _canonical
from nov_navigation_memory_sync import write_checkpoint
from nov_spatial_memory_sync import _observation_id, _validate_ack
import world_weather_control as control
from world_physical_weather import read_weather, WORLD, OUTPUT as WEATHER
from world_sky_clock import sky_clock

SCHEMA = "live-infinita-weather-memory-experiment/v1"
STATE = Path("/var/lib/live-infinita/weather/memory-experiment.json")
PUBLIC = Path("/var/www/live-infinita-godot/navigation-memory/weather-memory.json")
CACHE_LIMIT = 384
HISTORY_LIMIT = 128
MIN_MEMORIES = 3
ISSUE_WINDOW_MS = 10000
SCALES = {"temperature_c": 5.0, "humidity": 0.15, "cloud_coverage": 0.2,
          "wind_x_mps": 3.0, "wind_z_mps": 3.0}


def hierarchy(world_id): return f"live:weather:{world_id}:nov:observed-transition"


def check_transition(origin, observed):
    control.validate_sample(origin)
    control.validate_sample(observed)
    span = observed["time_ms"] - origin["time_ms"]
    if not control.HORIZON_MS <= span <= control.HORIZON_MS + control.TOLERANCE_MS:
        raise ValueError("weather_memory_observed_span")


def context_symbol(s):
    context = {k: round(s["values"][k] / scale) for k, scale in SCALES.items()}
    context["day_bin"] = int((s["time_ms"] % 3600000) // 300000)
    return int.from_bytes(blake2b(_canonical(context), digest_size=8).digest(), "big")


def transition_payload(world_id, duration, origin, observed):
    check_transition(origin, observed)
    if type(duration) is not int or not 1 <= duration <= 60000:
        raise ValueError("weather_memory_duration")
    observation = {"origin": origin, "observed": observed, "tick_duration_ms": duration}
    raw = _canonical(observation)
    event = {"version": 1, "source_id": f"live.infinita:{world_id}:nov:weather-observed",
             "sequence": observed["time_ms"], "byte_offset": 0, "byte_length": len(raw),
             "trail": [context_symbol(origin), context_symbol(observed)], "relation_ids": [],
             "signature": blake2b(raw, digest_size=8).hexdigest(), "resolution": 1}
    return {"event": event, "provenance": {"hierarchy_id": hierarchy(world_id),
            "source_kind": "observed_physical_weather_transition", "world_id": world_id,
            "entity_id": "nov", "observation_channel": "global_physical_weather_delivery",
            "observation": observation, "payload_sha256": sha256(raw).hexdigest(),
            "world_write_authority": False, "selection_authority": False,
            "contains_prediction": False, "chronological_episode": False}}


def request_api(path, payload=None):
    key = os.environ.get("MEMORIA_API_KEY", "")
    if len(key) < 32: raise ValueError("weather_memory_key_unconfigured")
    req = Request("http://127.0.0.1:8788" + path,
                  data=_canonical(payload) if payload is not None else None,
                  headers={"X-Memoria-Key": key, "Content-Type": "application/json", "Accept": "application/json"})
    with build_opener(ProxyHandler({})).open(req, timeout=5) as response:
        raw = response.read(2000001)
        if response.status != (201 if payload is not None else 200) or len(raw) > 2000000:
            raise ValueError("weather_memory_api_response")
    value = json.loads(raw)
    if not isinstance(value, dict): raise ValueError("weather_memory_api_contract")
    return value


def send_local(payload): return request_api("/api/v1/structural/observations?defer_associations=true", payload)
def fetch_local(): return request_api("/api/v1/structural/observations/recent?limit=64")


def decode_envelope(envelope, world_id, duration):
    if not isinstance(envelope, dict): raise ValueError("weather_memory_envelope")
    p = envelope.get("provenance", {})
    if not isinstance(p, dict): raise ValueError("weather_memory_provenance")
    if p.get("hierarchy_id") != hierarchy(world_id): return None
    obs = p.get("observation", {})
    if not isinstance(obs, dict): raise ValueError("weather_memory_observation")
    expected = transition_payload(world_id, duration, obs.get("origin"), obs.get("observed"))
    if p != expected["provenance"] or envelope.get("event") != expected["event"]:
        raise ValueError("weather_memory_content_mismatch")
    identity = _observation_id(expected["event"])
    if envelope.get("observation_id") != identity:
        raise ValueError("weather_memory_identity_mismatch")
    return {"observation_id": identity, "payload": expected}


def merge_recalled(cache, response, world_id, duration):
    if not isinstance(response, dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"), list) or len(response["items"]) > 100:
        raise ValueError("weather_memory_recall_contract")
    indexed = {row["observation_id"]: row for row in cache}
    for envelope in response["items"]:
        row = decode_envelope(envelope, world_id, duration)
        if row is not None: indexed[row["observation_id"]] = row
    return sorted(indexed.values(), key=lambda r: (r["payload"]["provenance"]["observation"]["observed"]["time_ms"], r["observation_id"]))[-CACHE_LIMIT:]


def predict(origin, cache):
    control.validate_sample(origin)
    candidates = []
    for row in cache:
        obs = row["payload"]["provenance"]["observation"]
        if obs["observed"]["time_ms"] > origin["time_ms"]: continue
        start = obs["origin"]
        phase = abs((start["time_ms"] - origin["time_ms"]) % 3600000) / 3600000
        phase = min(phase, 1-phase)
        distance = sum(((start["values"][k]-origin["values"][k])/SCALES[k])**2 for k in SCALES) + (phase/0.2)**2
        candidates.append((distance, row["observation_id"], obs))
    if len(candidates) < MIN_MEMORIES: return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    selected = candidates[:MIN_MEMORIES]
    weights = [1.0/(1.0+d) for d, _, _ in selected]
    total = sum(weights)
    predicted = {}
    for k, (low, high) in control.FIELDS.items():
        delta = sum(w*(obs["observed"]["values"][k]-obs["origin"]["values"][k])*control.HORIZON_MS/(obs["observed"]["time_ms"]-obs["origin"]["time_ms"]) for w, (_, _, obs) in zip(weights, selected))/total
        predicted[k] = min(high, max(low, origin["values"][k]+delta))
    speed = math.hypot(predicted["wind_x_mps"], predicted["wind_z_mps"])
    if speed > 8:
        for k in ("wind_x_mps", "wind_z_mps"): predicted[k] *= 8/speed
    return {"method": "retrieved_observed_transition_analog", "values": predicted,
            "memory_used": True, "source": "memoria.ia-local-structural-api-confirmed-cache",
            "supports": [{"observation_id": identity, "weight": w/total,
                          "observed_end_ms": obs["observed"]["time_ms"]} for w, (_, identity, obs) in zip(weights, selected)]}


def initial(world_id, duration):
    return {"schema": SCHEMA, "world_id": world_id, "tick_duration_ms": duration,
            "last_archived_end_ms": -1, "last_considered_control_id": None,
            "last_time_ms": -1, "cache": [], "pending": None, "paired": 0,
            "unavailable": 0, "missed": 0, "api_failures": 0, "last_reason": "starting",
            "error_sums": {method: {**{k: 0.0 for k in control.FIELDS}, "wind_vector_mps": 0.0} for method in ("control", "memory")},
            "memory_wins": {k: 0 for k in [*control.FIELDS, "wind_vector_mps"]}, "history": []}


def checksum(s): return sha256(_canonical({k: v for k, v in s.items() if k != "checksum"})).hexdigest()


def validate_state(s, world_id, duration):
    if not isinstance(s, dict) or s.get("schema") != SCHEMA or s.get("world_id") != world_id or s.get("tick_duration_ms") != duration or s.get("checksum") != checksum(s):
        raise ValueError("weather_memory_checkpoint_identity")
    if not isinstance(s.get("cache"), list) or len(s["cache"]) > CACHE_LIMIT or not isinstance(s.get("history"), list) or len(s["history"]) > HISTORY_LIMIT:
        raise ValueError("weather_memory_checkpoint_budget")
    for k in ("paired", "unavailable", "missed", "api_failures"):
        if type(s.get(k)) is not int or not 0 <= s[k] <= 1000000000: raise ValueError("weather_memory_counter")
    for k in ("last_time_ms", "last_archived_end_ms"):
        if type(s.get(k)) is not int or s[k] < -1: raise ValueError("weather_memory_cursor")
    pending = s.get("pending")
    if pending is not None:
        control.validate_trial(pending["control"], world_id, duration)
        trial = pending["control"]
        logical = pending.get("issued_logical_time_ms")
        if type(logical) is not int or not trial["origin"]["time_ms"] <= logical <= trial["origin"]["time_ms"] + ISSUE_WINDOW_MS or logical >= trial["target_time_ms"]:
            raise ValueError("weather_memory_pending_causality")
        forecast = pending["forecast"]
        control.validate_sample({"time_ms":trial["target_time_ms"],"values":forecast["values"]})
        if forecast.get("memory_used") is not True or forecast.get("method") != "retrieved_observed_transition_analog" or forecast.get("source") != "memoria.ia-local-structural-api-confirmed-cache":
            raise ValueError("weather_memory_pending_source")
        supports = forecast.get("supports")
        if not isinstance(supports, list) or len(supports) != MIN_MEMORIES:
            raise ValueError("weather_memory_pending_supports")
        for support in supports:
            if not isinstance(support.get("observation_id"), str) or not support["observation_id"].startswith("structural-event:") or type(support.get("observed_end_ms")) is not int or not 0 <= support["observed_end_ms"] <= trial["origin"]["time_ms"] or type(support.get("weight")) not in (int,float) or not math.isfinite(support["weight"]) or not 0 < support["weight"] <= 1:
                raise ValueError("weather_memory_pending_support_causality")
        if len({r["observation_id"] for r in supports}) != MIN_MEMORIES or abs(sum(r["weight"] for r in supports)-1) > 1e-9:
            raise ValueError("weather_memory_pending_weights")
    for row in s["cache"]:
        if decode_envelope({**row["payload"], "observation_id": row["observation_id"]}, world_id, duration) is None:
            raise ValueError("weather_memory_cached_hierarchy")
    for sums in s["error_sums"].values():
        for v in sums.values():
            if type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1e12:
                raise ValueError("weather_memory_error_sum")
    return s


def score_pair(state, completed):
    pending = state["pending"]
    if pending is None: return
    baseline = pending["control"]
    found = next((row for row in completed if row["trial"]["prediction_id"] == baseline["prediction_id"]), None)
    if found is None: return
    observed = found["observed"]
    check_transition(baseline["origin"], observed)
    errors = {}
    for method, values in (("control", baseline["prediction"]), ("memory", pending["forecast"]["values"])):
        errors[method] = {k: abs(observed["values"][k]-values[k]) for k in control.FIELDS}
        errors[method]["wind_vector_mps"] = math.hypot(errors[method]["wind_x_mps"], errors[method]["wind_z_mps"])
        for k, value in errors[method].items(): state["error_sums"][method][k] += value
    for k in errors["memory"]:
        if errors["memory"][k] < errors["control"][k]-1e-12: state["memory_wins"][k] += 1
    state["paired"] += 1
    state["history"].append({"prediction": pending, "observed": observed, "errors": errors})
    state["history"] = state["history"][-HISTORY_LIMIT:]
    state["pending"] = None


def summary(s, now):
    n = s["paired"]
    means = {m: {k: v/n if n else None for k, v in sums.items()} for m, sums in s["error_sums"].items()}
    return {"schema": SCHEMA, "world_id": s["world_id"], "generated_at_unix": now,
            "source": "prospective_paired_weather_memory_experiment", "paired": n,
            "unavailable": s["unavailable"], "missed": s["missed"], "api_failures": s["api_failures"],
            "last_reason": s["last_reason"], "recalled_memories": len(s["cache"]),
            "mean_absolute_error": means, "memory_wins": s["memory_wins"],
            "pending": s["pending"], "last_evaluation": s["history"][-1] if s["history"] else None,
            "inference_location": "application_bounded_analog_predictor",
            "observation_channel": "global_physical_weather_delivery",
            "inference_influence": False, "world_write_authority": False}


def publish(world=WORLD, weather=WEATHER, base_state=control.STATE, base_public=control.PUBLIC,
            state=STATE, public=PUBLIC, clock=WORLD.with_name("simulation-clock.json"),
            send=send_local, fetch=fetch_local, now=time.time):
    world_id = _read_json(world, 2*1024*1024, "weather_memory_world").get("world_id")
    stamp = now()
    observation = read_weather(weather, world_id, now=lambda: stamp)
    if observation is None: raise ValueError("weather_memory_weather_unavailable")
    duration = observation["tick_duration_ms"]
    baseline = _read_json(base_state, 2*1024*1024, "weather_memory_control") if base_state.exists() else control.initial(world_id, duration)
    baseline = control.process(baseline, observation, world_id, duration, stamp)
    # Preserve the standalone control even when the memory API is unavailable.
    write_checkpoint(base_state, baseline)
    write_checkpoint(base_public, control.summary(baseline, stamp), mode=0o644)
    saved = _read_json(state, 2*1024*1024, "weather_memory_state") if state.exists() else None
    s = validate_state(saved, world_id, duration) if saved is not None else initial(world_id, duration)
    if observation["time_ms"] < s["last_time_ms"]: raise ValueError("weather_memory_clock_rewind")
    score_pair(s, baseline["history"])
    trial = baseline["pending"]
    if s["pending"] is not None and s["pending"]["control"]["prediction_id"] != trial["prediction_id"]:
        s["missed"] += 1
        s["pending"] = None
    considering = False
    try:
        # At most one confirmed physical transition submitted per invocation.
        row = next((r for r in baseline["history"] if r["observed"]["time_ms"] > s["last_archived_end_ms"]), None)
        if row is not None:
            payload = transition_payload(world_id, duration, row["trial"]["origin"], row["observed"])
            response = send(payload)
            _validate_ack(response, payload)
            if response["stored"] == response["duplicate"]: raise ValueError("weather_memory_ack_status")
            s["last_archived_end_ms"] = row["observed"]["time_ms"]
        if s["last_considered_control_id"] != trial["prediction_id"]:
            considering = True
            s["last_considered_control_id"] = trial["prediction_id"]
            s["cache"] = merge_recalled(s["cache"], fetch(), world_id, duration)
            forecast = predict(trial["origin"], s["cache"])
            c = sky_clock(clock, world_id)
            logical = c["logical_time_ms"] if c is not None else None
            if logical is None or not trial["origin"]["time_ms"] <= logical <= trial["origin"]["time_ms"] + ISSUE_WINDOW_MS or logical >= trial["target_time_ms"]:
                s["unavailable"] += 1; s["last_reason"] = "issuance_window_unavailable"
            elif forecast is None:
                s["unavailable"] += 1; s["last_reason"] = "insufficient_retrieved_memories"
            else:
                s["pending"] = {"control": deepcopy(trial), "forecast": forecast,
                                "issued_at_unix": now(), "issued_logical_time_ms": logical}
                s["last_reason"] = "memory_prediction_committed"
    except (OSError, ValueError, RuntimeError, TimeoutError):
        s["api_failures"] += 1
        s["last_reason"] = "memory_api_or_contract_unavailable"
        if considering and s["pending"] is None:
            s["unavailable"] += 1
    s["last_time_ms"] = observation["time_ms"]
    s["checksum"] = checksum(s)
    validate_state(s, world_id, duration)
    write_checkpoint(state, s)
    write_checkpoint(public, summary(s, now()), mode=0o644)
    return {"paired": s["paired"], "recalled": len(s["cache"]), "reason": s["last_reason"], "inference_influence": False}


if __name__ == "__main__": print(json.dumps(publish(), sort_keys=True))
