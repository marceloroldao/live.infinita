#!/usr/bin/env python3
"""Summarize observed native journey attempts without writing world or memory."""
import argparse
import collections
import json
import math
import pathlib
import statistics
import subprocess
import sys
import time

SCHEMA = "live-infinita-nov-journey-attempt/v1"
PREFIX = "NOV_JOURNEY_ATTEMPT "
MAX_BYTES = 10 * 1024 * 1024
MAX_EVENTS = 10000
REASONS = {"arrived", "stuck_recovery", "goal_changed", "world_changed",
           "goal_idle_timeout", "goal_hard_timeout", "goal_ended",
           "search_intent_changed", "feed_unavailable", "renderer_shutdown", "interrupted"}
COUNTERS = ("blocked_attempts", "completed_steps", "causal_ram_steps", "causal_memoria_steps")

def number(value, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid finite number")
    if nonnegative and value < 0:
        raise ValueError("negative value")
    return value

def integer(value):
    value = number(value)
    if value != int(value):
        raise ValueError("invalid integer")
    return int(value)

def point(value, optional=False):
    if value is None and optional:
        return
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("invalid XZ point")
    for item in value:
        number(item, False)

def validate(row):
    if not isinstance(row, dict) or row.get("schema") != SCHEMA:
        raise ValueError("unexpected schema")
    required = {"world_id", "goal_id", "quality_eligible", "goal", "start", "current", "initial_remaining_m", "remaining_m", "started_at_unix", "started_monotonic_ms", "distance_m", "duration_monotonic_ms", "event"} | set(COUNTERS)
    if not required.issubset(row):
        raise ValueError("missing attempt fields")
    if row.get("world_write_authority") is not False or row.get("learning_evidence") is not False:
        raise ValueError("unexpected authority")
    for key in ("world_id", "goal_id"):
        if not isinstance(row.get(key), str) or not row[key] or len(row[key]) > 256:
            raise ValueError("invalid identity")
    if type(row.get("quality_eligible")) is not bool:
        raise ValueError("invalid quality flag")
    point(row.get("goal"))
    point(row.get("start"), True)
    point(row.get("current"), True)
    for key in ("initial_remaining_m", "remaining_m"):
        if row.get(key) is not None:
            number(row[key])
    for key in ("started_at_unix", "distance_m"):
        number(row.get(key))
    for key in ("started_monotonic_ms", "duration_monotonic_ms") + COUNTERS:
        integer(row.get(key))
    if row["causal_ram_steps"] > row["completed_steps"] or row["causal_memoria_steps"] > row["completed_steps"]:
        raise ValueError("causal steps exceed completed steps")
    if row.get("event") == "started":
        if row["distance_m"] != 0 or any(row[k] for k in COUNTERS):
            raise ValueError("start has completed movement")
    elif row.get("event") == "ended":
        if row.get("termination") not in REASONS:
            raise ValueError("unknown termination")
        number(row.get("ended_at_unix"))
        end = integer(row.get("ended_monotonic_ms"))
        # Snapshot and timestamp are separate calls in 008EA; allow up to 5 ms.
        if end < row["started_monotonic_ms"]:
            raise ValueError("end before start")
        if abs(end - row["started_monotonic_ms"] - row["duration_monotonic_ms"]) > 5:
            raise ValueError("inconsistent monotonic duration")
        if row["termination"] != "arrived" and row["quality_eligible"]:
            raise ValueError("interruption cannot be quality eligible")
        if row["termination"] == "arrived" and (row["remaining_m"] is None or row["remaining_m"] >= 0.1):
            raise ValueError("arrival outside recorded goal tolerance")
    else:
        raise ValueError("unknown event")

def summarize(text, now=None):
    if len(text.encode("utf-8")) > MAX_BYTES:
        raise ValueError("journal input too large")
    starts, ends = {}, {}
    duplicates = 0
    count = 0
    for line in text.splitlines():
        if not line.startswith(PREFIX):
            continue
        count += 1
        if count > MAX_EVENTS:
            raise ValueError("too many events")
        row = json.loads(line[len(PREFIX):])
        validate(row)
        key = (row["world_id"], row["goal_id"])
        table = starts if row["event"] == "started" else ends
        if key in table:
            if table[key] != row:
                raise ValueError("conflicting duplicate event")
            duplicates += 1
        else:
            table[key] = row
    paired = []
    for key in starts.keys() & ends.keys():
        start, end = starts[key], ends[key]
        for field in ("goal", "start", "initial_remaining_m", "started_at_unix", "started_monotonic_ms"):
            if start[field] != end[field]:
                raise ValueError("start/end metadata mismatch")
        paired.append(end)
    paired.sort(key=lambda x: (x["started_at_unix"], x["world_id"], x["goal_id"]))
    reasons = dict(collections.Counter(x["termination"] for x in paired))
    arrived = [x for x in paired if x["termination"] == "arrived"]
    def metrics(rows):
        if not rows:
            return {"count": 0, "duration_mean_seconds": None, "duration_median_seconds": None,
                    "distance_sum_m": 0, "distance_mean_m": None}
        duration = [x["duration_monotonic_ms"] / 1000 for x in rows]
        distance = [x["distance_m"] for x in rows]
        return {"count": len(rows), "duration_mean_seconds": round(statistics.mean(duration), 3),
                "duration_median_seconds": round(statistics.median(duration), 3),
                "distance_sum_m": round(sum(distance), 3),
                "distance_mean_m": round(statistics.mean(distance), 3)}
    return {"schema": "live-infinita-journey-attempt-audit/v1",
            "generated_at_unix": time.time() if now is None else now, "read_only": True,
            "counts": {"started": len(starts), "ended": len(ends), "paired": len(paired),
                       "arrived": len(arrived), "interrupted": len(paired) - len(arrived),
                       "open_or_censored": len(starts.keys() - ends.keys()),
                       "end_without_start_in_window": len(ends.keys() - starts.keys()),
                       "identical_duplicates_ignored": duplicates},
            "termination_counts": reasons, "all_paired_attempts": metrics(paired),
            "arrivals": metrics(arrived),
            "interruptions": metrics([x for x in paired if x["termination"] != "arrived"]),
            "observed_arrival_fraction_among_paired": len(arrived) / len(paired) if paired else None,
            "quality_eligible_arrivals": sum(x["quality_eligible"] for x in arrived),
            "paired_attempts": paired,
            "open_or_censored_ids": [{"world_id": k[0], "goal_id": k[1]}
                                     for k in sorted(starts.keys() - ends.keys())],
            "end_without_start_ids": [{"world_id": k[0], "goal_id": k[1]}
                                      for k in sorted(ends.keys() - starts.keys())],
            "limitations": ["Window boundaries or abrupt restart can leave unmatched records.",
                            "Unmatched starts are not failures; unmatched ends are excluded from paired metrics.",
                            "Arrival fraction describes paired records, not all starts or a survival estimate.",
                            "Distances are planar physical travel; duration is process monotonic real time.",
                            "Different goals and terrain prevent a causal policy comparison.",
                            "Recorded causal steps do not prove outcome improvement."],
            "memory_advantage_demonstrated": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=pathlib.Path, help="plain journalctl -o cat text")
    parser.add_argument("--since", default="2 hours ago", help="journal window when --file is absent")
    args = parser.parse_args()
    if args.file:
        if args.file.stat().st_size > MAX_BYTES:
            raise ValueError("journal input too large")
        source = args.file.read_text()
        scope = {"type": "supplied_journal_text", "path": str(args.file)}
    else:
        result = subprocess.run(["journalctl", "-u", "live-infinita-renderer.service",
                                 "--since", args.since, "-n", str(MAX_EVENTS),
                                 "--no-pager", "-o", "cat"], capture_output=True, text=True,
                                check=True, timeout=30)
        source = result.stdout
        scope = {"type": "native_renderer_journal", "since": args.since,
                 "max_journal_lines": MAX_EVENTS}
    result = summarize(source)
    result["source_scope"] = scope
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print("Journey audit failed: " + str(exc), file=sys.stderr)
        sys.exit(1)
