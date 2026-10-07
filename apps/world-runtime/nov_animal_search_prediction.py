"""Bounded shadow forecasts from encounters already stored AND recovered in Memoria.ia.

Reads the native eye outbox and its sealed verification ACK. Never reads wildlife
positions, habitat, needs or destinations. Forecasts do not enter the memory
observation trail and do not drive navigation. Scores are not probabilities.
"""
from hashlib import sha256
import json
import math
from pathlib import Path
import time
from nov_animal_memory_sync import (
    SOURCE, ACK, WORLD, MAX_BYTES, read_source, read_ack, validate_record,
    payload, integer, number, point,
)
from nov_spatial_memory_sync import _canonical, _observation_id, _world_id
from nov_navigation_memory_sync import write_checkpoint

STATE = Path("/var/lib/live-infinita/wildlife/search-predictions.json")
PUBLIC = Path("/var/www/live-infinita-godot/wildlife/search-predictions.json")
SCHEMA = "live-infinita-nov-animal-search/v1"
CYCLE_MS = 3600000
HORIZON_MS = 60000
ACK_GRACE_MS = 180000
SEPARATION_MS = 30000
MAX_AGE_MS = 6 * CYCLE_MS
CELL_M = 8
RADIUS_M = 8
MAX_STATE_BYTES = 100000


def sealed(value):
    raw = _canonical(value).decode()
    return {"payload": raw, "sha256": sha256(raw.encode()).hexdigest()}


def verified_records(source, ack, now_unix):
    """Recheck provenance-derived identity; sample_count never becomes support."""
    rows = []
    ids = set()
    previous = 0
    entity_last = {}
    for item in ack["verified_history"]:
        if not isinstance(item, dict):
            raise ValueError("animal_search_history_fields")
        row = validate_record(item.get("encounter"), source["world_id"])
        seq = int(row["sequence"])
        if not previous < seq <= ack["cursor"] or row["last_seen_ms"] > source["logical_time_ms"]:
            raise ValueError("animal_search_history_time_or_sequence")
        previous = seq
        if row["first_seen_ms"] < entity_last.get(row["entity_id"], 0):
            raise ValueError("animal_search_history_overlap")
        entity_last[row["entity_id"]] = row["last_seen_ms"]
        number(item.get("verified_at_unix"), 0, now_unix + 30)
        expected_id = _observation_id(payload(source["world_id"], source["session_id"], row)["event"])
        if item.get("observation_id") != expected_id or expected_id in ids:
            raise ValueError("animal_search_history_identity")
        ids.add(expected_id)
        rows.append({"observation_id": expected_id, "encounter": row})
    return rows


def regions(rows, entity, logical_ms):
    """Independent visits per 8m cell, ranked by recurrence, age and day phase."""
    groups = {}
    cluster_end = {}
    for item in rows:
        row = item["encounter"]
        age = logical_ms - row["last_seen_ms"]
        if row["entity_id"] != entity or not 0 <= age <= MAX_AGE_MS:
            continue
        pos = row["last_target_m"]
        cell = (math.floor(pos[0] / CELL_M), math.floor(pos[2] / CELL_M))
        group = groups.setdefault(cell, [])
        # Continuous window splits and brief contact losses aren't new visits.
        gap = row["first_seen_ms"] - cluster_end.get(cell, -SEPARATION_MS)
        cluster_end[cell] = row["last_seen_ms"]
        if gap < SEPARATION_MS:
            continue
        group.append(item)
    candidates = []
    phase = ((logical_ms + HORIZON_MS) % CYCLE_MS) / CYCLE_MS
    for cell, visits in groups.items():
        if len(visits) < 3:
            continue
        weight = 0.0
        for item in visits:
            row = item["encounter"]
            age = logical_ms - row["last_seen_ms"]
            seen_phase = (row["last_seen_ms"] % CYCLE_MS) / CYCLE_MS
            delta = abs(seen_phase - phase)
            delta = min(delta, 1 - delta)
            weight += math.exp(-age / (2 * CYCLE_MS)) * (0.25 + 0.75 * math.exp(-0.5 * (delta / 0.125) ** 2))
        candidates.append({
            "center_xz_m": [(cell[0] + 0.5) * CELL_M, (cell[1] + 0.5) * CELL_M],
            "radius_m": RADIUS_M, "independent_encounters": len(visits),
            "recurrence_score": round(weight, 6),
            "evidence_ids": [item["observation_id"] for item in visits],
        })
    return sorted(candidates, key=lambda c: (-c["recurrence_score"], c["center_xz_m"]))[:3]


def initial_state(source):
    return {
        "schema": SCHEMA, "world_id": source["world_id"], "session_id": source["session_id"],
        "logical_time_ms": 0, "pending": [], "last_issue": {}, "evaluations": [],
        "counters": {"issued": 0, "paired": 0, "memory_hits": 0, "last_seen_hits": 0,
                     "expired_without_observation": 0, "memory_distance_sum_m": 0.0,
                     "last_seen_distance_sum_m": 0.0},
    }


def validate_forecast(value, source):
    if not isinstance(value, dict):
        raise ValueError("animal_search_forecast")
    entity = value.get("entity_id")
    if not isinstance(entity, str) or not entity.startswith(source["world_id"] + ":rabbit:"):
        raise ValueError("animal_search_forecast_entity")
    issued = integer(value.get("issued_ms"))
    if integer(value.get("expires_ms")) != issued + HORIZON_MS:
        raise ValueError("animal_search_forecast_horizon")
    for name in ("center_xz_m", "last_seen_xz_m"):
        p = value.get(name)
        if not isinstance(p, list) or len(p) != 2:
            raise ValueError("animal_search_forecast_point")
        for coordinate in p:
            number(coordinate, -100000, 100000)
    if value.get("radius_m") != RADIUS_M or value.get("contains_prediction") is not True:
        raise ValueError("animal_search_forecast_authority")
    ids = value.get("evidence_ids")
    if not isinstance(ids, list) or not 3 <= len(ids) <= 16 or len(set(ids)) != len(ids):
        raise ValueError("animal_search_forecast_support")
    if any(not isinstance(v, str) or not v.startswith("structural-event:") for v in ids):
        raise ValueError("animal_search_forecast_evidence")
    signature = {k: v for k, v in value.items() if k != "forecast_id"}
    if value.get("forecast_id") != sha256(_canonical(signature)).hexdigest():
        raise ValueError("animal_search_forecast_identity")


def read_state(path, source):
    if not path.exists():
        return initial_state(source)
    if path.is_symlink() or path.stat().st_size > MAX_STATE_BYTES:
        raise ValueError("animal_search_state_path_or_budget")
    envelope = json.loads(path.read_bytes())
    raw = envelope.get("payload")
    if not isinstance(raw, str) or envelope.get("sha256") != sha256(raw.encode()).hexdigest():
        raise ValueError("animal_search_state_checksum")
    value = json.loads(raw)
    if value.get("schema") != SCHEMA or value.get("world_id") != source["world_id"] or value.get("session_id") != source["session_id"]:
        raise ValueError("animal_search_state_identity")
    previous = integer(value.get("logical_time_ms"))
    if source["logical_time_ms"] < previous:
        raise ValueError("animal_search_clock_rewind")
    pending = value.get("pending")
    if not isinstance(pending, list) or len(pending) > 16:
        raise ValueError("animal_search_state_pending")
    entities = set()
    for forecast in pending:
        validate_forecast(forecast, source)
        if forecast["issued_ms"] > previous or forecast["entity_id"] in entities:
            raise ValueError("animal_search_state_forecast_time")
        entities.add(forecast["entity_id"])
    last_issue = value.get("last_issue")
    if not isinstance(last_issue, dict) or len(last_issue) > 16:
        raise ValueError("animal_search_state_issues")
    for entity, stamp in last_issue.items():
        if not entity.startswith(source["world_id"] + ":rabbit:") or integer(stamp) > previous:
            raise ValueError("animal_search_state_issue")
    evaluations = value.get("evaluations")
    if not isinstance(evaluations, list) or len(evaluations) > 32:
        raise ValueError("animal_search_state_evaluations")
    counters = value.get("counters")
    keys = set(initial_state(source)["counters"])
    if not isinstance(counters, dict) or set(counters) != keys:
        raise ValueError("animal_search_state_counters")
    for key, val in counters.items():
        if key.endswith("sum_m"):
            number(val, 0, 10**15)
        else:
            integer(val)
    if counters["paired"] > counters["issued"] or max(counters["memory_hits"], counters["last_seen_hits"]) > counters["paired"]:
        raise ValueError("animal_search_state_counter_consistency")
    return value


def advance(state, source, rows):
    now = int(source["logical_time_ms"])
    c = state["counters"]
    pending = []
    for forecast in state["pending"]:
        future = [item for item in rows if item["encounter"]["entity_id"] == forecast["entity_id"]
                  and forecast["issued_ms"] < item["encounter"]["first_seen_ms"] <= forecast["expires_ms"]]
        if future:
            item = min(future, key=lambda x: x["encounter"]["first_seen_ms"])
            row = item["encounter"]
            observed = [row["first_target_m"][0], row["first_target_m"][2]]
            memory_distance = math.dist(observed, forecast["center_xz_m"])
            baseline_distance = math.dist(observed, forecast["last_seen_xz_m"])
            c["paired"] += 1
            c["memory_hits"] += int(memory_distance <= RADIUS_M)
            c["last_seen_hits"] += int(baseline_distance <= RADIUS_M)
            c["memory_distance_sum_m"] += memory_distance
            c["last_seen_distance_sum_m"] += baseline_distance
            state["evaluations"].append({
                "forecast_id": forecast["forecast_id"], "observation_id": item["observation_id"],
                "issued_ms": forecast["issued_ms"], "observed_ms": row["first_seen_ms"],
                "memory_distance_m": memory_distance, "last_seen_distance_m": baseline_distance,
                "memory_hit": memory_distance <= RADIUS_M, "last_seen_hit": baseline_distance <= RADIUS_M,
            })
        elif now > forecast["expires_ms"] + ACK_GRACE_MS:
            # No sighting is not proof of absence. Not included in paired scores.
            c["expired_without_observation"] += 1
        else:
            pending.append(forecast)
    state["pending"] = pending
    state["evaluations"] = state["evaluations"][-32:]
    occupied = {f["entity_id"] for f in pending}
    entities = sorted({item["encounter"]["entity_id"] for item in rows})
    for entity in entities:
        if entity in occupied or len(pending) >= 16 or now - state["last_issue"].get(entity, -HORIZON_MS) < HORIZON_MS:
            continue
        ranked = regions(rows, entity, now)
        if not ranked:
            continue
        if entity not in state["last_issue"] and len(state["last_issue"]) >= 16:
            continue
        best = ranked[0]
        last = max((item["encounter"] for item in rows if item["encounter"]["entity_id"] == entity), key=lambda r: r["last_seen_ms"])
        forecast = {
            "entity_id": entity, "issued_ms": now, "expires_ms": now + HORIZON_MS,
            "center_xz_m": best["center_xz_m"], "radius_m": RADIUS_M,
            "last_seen_xz_m": [last["last_target_m"][0], last["last_target_m"][2]],
            "evidence_ids": best["evidence_ids"], "contains_prediction": True,
        }
        forecast["forecast_id"] = sha256(_canonical(forecast)).hexdigest()
        validate_forecast(forecast, source)
        pending.append(forecast)
        state["last_issue"][entity] = now
        c["issued"] += 1
    state["logical_time_ms"] = now
    return state


def run_once(source=SOURCE, ack=ACK, world=WORLD, state_path=STATE, public=PUBLIC, now_unix=None):
    wall = time.time() if now_unix is None else now_unix
    world_id = _world_id(world)
    s = read_source(source, world_id, wall)
    a = read_ack(ack, s)
    rows = verified_records(s, a, wall)
    state = advance(read_state(state_path, s), s, rows)
    write_checkpoint(state_path, sealed(state))
    c = state["counters"]
    paired = c["paired"]
    status = {
        "schema": SCHEMA, "world_id": world_id, "generated_at_unix": wall,
        "logical_time_ms": s["logical_time_ms"], "contains_prediction": True,
        "source": "verified_recalled_eye_encounters", "model": "application_spatial_recurrence",
        "world_write_authority": False, "decision_use": False,
        "learning_improvement_measured": False, "absence_claim": False,
        "reason": "forecast_ready" if state["pending"] else "waiting_for_independent_encounters",
        "verified_history_window": len(rows), "history_window_limit": 16,
        "minimum_independent_encounters": 3, "independence_gap_ms": SEPARATION_MS,
        "forecast_horizon_ms": HORIZON_MS, "observation_ack_grace_ms": ACK_GRACE_MS,
        "max_evidence_age_ms": MAX_AGE_MS, "score_is_probability": False,
        "forecasts": state["pending"], "counters": c,
        "paired_metrics": {
            "memory_hit_rate": c["memory_hits"] / paired if paired else None,
            "last_seen_hit_rate": c["last_seen_hits"] / paired if paired else None,
            "memory_mean_distance_m": c["memory_distance_sum_m"] / paired if paired else None,
            "last_seen_mean_distance_m": c["last_seen_distance_sum_m"] / paired if paired else None,
        },
        "evaluations": state["evaluations"], "last_error": None,
    }
    write_checkpoint(public, status, 0o644)
    return status


def main():
    try:
        status = run_once()
    except Exception as exc:
        error = str(exc) if isinstance(exc, ValueError) and str(exc).startswith(("animal_search_", "animal_memory_")) else "animal_search_inputs_unavailable"
        status = {
            "schema": SCHEMA, "generated_at_unix": time.time(), "reason": "forecast_unavailable",
            "last_error": error, "forecasts": [], "contains_prediction": True,
            "world_write_authority": False, "decision_use": False,
            "learning_improvement_measured": False, "absence_claim": False,
        }
        write_checkpoint(PUBLIC, status, 0o644)
    print(json.dumps({k: v for k, v in status.items() if k not in ("forecasts", "evaluations")}, sort_keys=True))


if __name__ == "__main__":
    main()
