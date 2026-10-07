#!/usr/bin/env python3
"""Read-only audit of native animal searches; does not select goals or write memory."""
import argparse
import json
import math
import pathlib
import time

ARMS = ("memory", "last_seen")

def integer(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value != int(value):
        raise ValueError("invalid nonnegative integer")
    return int(value)

def audit(intent, memory, prediction, now=None):
    now = time.time() if now is None else now
    inputs = ((intent, "live-infinita-nov-animal-search-intent/v1", "native_bounded_animal_search", True),
              (memory, "live-infinita-nov-animal-memory/v1", None, False),
              (prediction, "live-infinita-nov-animal-search/v1", "verified_recalled_eye_encounters", False))
    world = intent.get("world_id")
    if not isinstance(world, str) or not world:
        raise ValueError("missing world")
    ages = {}
    for value, schema, source, decision in inputs:
        if value.get("schema") != schema or value.get("world_id") != world or value.get("world_write_authority") is not False or value.get("decision_use") is not decision or value.get("absence_claim", False if source is None else None) is not False or value.get("last_error") is not None:
            raise ValueError("invalid identity, authority or source error")
        if source and value.get("source") != source:
            raise ValueError("unexpected source")
        stamp = value.get("generated_at_unix")
        if isinstance(stamp, bool) or not isinstance(stamp, (int, float)) or not math.isfinite(stamp):
            raise ValueError("invalid timestamp")
        age = now - stamp
        if not -5 <= age <= 15:
            raise ValueError("stale or future status")
        ages[schema] = round(age, 3)
    active = intent.get("active")
    if not isinstance(active, bool):
        raise ValueError("invalid active flag")
    arms = {}
    total_pending = 0
    for arm in ARMS:
        count = {k: integer(intent["counts"][arm][k]) for k in ("started", "confirmed", "not_observed", "aborted")}
        completed = count["confirmed"] + count["not_observed"] + count["aborted"]
        pending = count["started"] - completed
        if pending not in (0, 1):
            raise ValueError("inconsistent outcome totals")
        total_pending += pending
        arms[arm] = dict(count, completed=completed, pending=pending,
                         confirmed_per_completed=count["confirmed"] / completed if completed else None)
    if total_pending != int(active):
        raise ValueError("active intent does not match counters")
    if active:
        arm = intent.get("intent", {}).get("arm")
        if arm not in ARMS or arms[arm]["pending"] != 1:
            raise ValueError("active strategy does not match pending count")
    history = memory.get("verified_history", [])
    if not isinstance(history, list):
        raise ValueError("invalid verified history")
    rows = intent.get("results", [])
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError("invalid result window")
    recent = []
    ids = set()
    window_counts = {arm: {"confirmed": 0, "not_observed": 0, "aborted": 0} for arm in ARMS}
    for row in rows:
        identity, arm = row.get("id"), row.get("arm")
        if not isinstance(identity, str) or not identity.startswith(world + ":animal-search:") or identity in ids or arm not in ARMS:
            raise ValueError("duplicate or invalid attempt")
        ids.add(identity)
        start, end, deadline = [integer(row[k]) for k in ("started_ms", "ended_ms", "deadline_ms")]
        if end < start or not start < deadline <= start + 45000:
            raise ValueError("invalid attempt time")
        confirmed = row.get("confirmed_by_eye_sensor")
        if not isinstance(confirmed, bool) or row.get("absence_claim") is not False or confirmed != (row.get("result") == "animal_seen"):
            raise ValueError("inconsistent physical confirmation")
        if confirmed and not start < end <= deadline:
            raise ValueError("confirmation outside attempt")
        category = "confirmed" if confirmed else ("not_observed" if row.get("result") == "not_observed_within_budget" else "aborted")
        window_counts[arm][category] += 1
        matches = [h for h in history if isinstance(h, dict) and isinstance(h.get("encounter"), dict)
                   and h["encounter"].get("entity_id") == row.get("entity_id")
                   and h["encounter"].get("first_seen_ms") == end] if confirmed else []
        recent.append({"id": identity, "arm": arm, "result": row["result"],
                       "duration_logical_ms": end - start, "confirmed_by_eye_sensor": confirmed,
                       "matching_recovered_encounter_ids": [h["observation_id"] for h in matches],
                       "recovery_check": "matched" if matches else ("not_in_current_history_window" if confirmed else "not_applicable")})
    for arm in ARMS:
        for category, count in window_counts[arm].items():
            if count > arms[arm][category]:
                raise ValueError("result window exceeds cumulative counters")
    return {"schema": "live-infinita-animal-search-audit/v1", "generated_at_unix": now,
            "world_id": world, "source_age_seconds": ages, "read_only": True,
            "bounded_search": {"arms": arms, "recent_results": recent,
                               "duration_scope": "recent_results_only_max_16",
                               "comparison_state": "both_strategies_observed" if all(arms[a]["completed"] for a in ARMS) else "waiting_for_both_strategies",
                               "allocation": "persisted_alternation_not_randomized"},
            "stored_and_recovered_encounters": integer(memory["stored_and_recovered_encounters"]),
            "shadow_prediction": {"counters": prediction["counters"], "paired_metrics": prediction["paired_metrics"],
                                  "observation_selection_affected_by_active_search": True},
            "memory_advantage_demonstrated": False,
            "general_learning_improvement_demonstrated": False}

def load(path):
    if path.stat().st_size > 131072:
        raise ValueError("oversized source")
    return json.loads(path.read_text())

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public-dir", type=pathlib.Path, default=pathlib.Path("/var/www/live-infinita-godot/wildlife"))
    args = parser.parse_args()
    try:
        result = audit(*[load(args.public_dir / name) for name in ("search-intent.json", "encounter-memory.json", "search-predictions.json")])
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, "Animal search audit unavailable: " + str(exc) + "\n")
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))

if __name__ == "__main__":
    main()
