"""MVP-018M: evaluate REDACTED owner canary metrics, not private evidence.

This is a deployment/observability gate, NOT a cognitive score. It never reads
the V2 DB, world state, raw episode logs, or hidden outcomes. Thresholds are
operator safety margins for a finite independent read-only canary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
from typing import Any

from nov_memory_continuous import PUBLIC_STATUSES, SCHEMA

EXPECTED_CYCLES = 60
MAX_LOG_BYTES = 128 * 1024
MAX_OWNER_RSS_KIB = 384 * 1024
MAX_STEP_MS = 250.0
MIN_READY_READS = 12
MIN_READY_FRACTION = 0.30
MAX_NOT_READY_STREAK = 20
MIN_TICK_ADVANCES = 5


def _is_uint(value: Any) -> bool:
    return type(value) is int and value >= 0


def evaluate_operational(report: dict[str, Any]) -> dict[str, Any]:
    """Only enumerated failure codes, never arbitrary input, enter output."""
    reasons: list[str] = []
    if not isinstance(report, dict) or report.get("schema") != SCHEMA:
        return {"status": "blocked", "reasons": ["schema_invalid"]}
    for name, expected in (
        ("historical_snapshot_only", True),
        ("live_caught_up_claim", False),
        ("main_runtime_wired", False),
        ("selection_authority", False),
        ("world_mutated", False),
        ("central_sync", False),
        ("bdr_used", False),
    ):
        if report.get(name) is not expected:
            reasons.append("authority_contract")
            break
    expected_uints = (
        "cycles", "samples", "ready_reads", "abstentions", "submissions",
        "longest_not_ready_streak", "frame_tick_advances", "frame_tick_regressions",
        "peak_rss_kib",
    )
    if any(not _is_uint(report.get(name)) for name in expected_uints):
        return {"status": "blocked", "reasons": ["metrics_invalid"]}
    if (report["cycles"] != EXPECTED_CYCLES or report["samples"] < EXPECTED_CYCLES
            or report["ready_reads"] + report["abstentions"] != report["samples"]
            or report["submissions"] > report["samples"]
            or report.get("status") != "ok"):
        reasons.append("accounting_invalid")
    counts = report.get("status_counts")
    if (not isinstance(counts, dict)
            or any(not isinstance(key, str) or key not in PUBLIC_STATUSES
                   or not _is_uint(value) for key, value in counts.items())
            or sum(counts.values()) != report["samples"]
            or counts.get("ready", 0) != report["ready_reads"]):
        reasons.append("status_accounting_invalid")
    fraction = report.get("ready_fraction")
    if (type(fraction) not in (int, float) or not 0 <= fraction <= 1
            or abs(fraction - (
                report["ready_reads"] / report["samples"] if report["samples"] else 0
            )) > 0.0001):
        reasons.append("readiness_fraction_invalid")
    if (report["ready_reads"] < MIN_READY_READS
            or (report["samples"] and
                report["ready_reads"] / report["samples"] < MIN_READY_FRACTION)
            or report["longest_not_ready_streak"] > MAX_NOT_READY_STREAK):
        reasons.append("readiness_budget")
    if (report["submissions"] < 2
            or report["frame_tick_advances"] < MIN_TICK_ADVANCES
            or report["frame_tick_regressions"] > 0):
        reasons.append("frame_progress_budget")
    step = report.get("max_step_ms")
    median = report.get("median_step_ms")
    if (type(step) not in (int, float) or type(median) not in (int, float)
            or not 0 <= median <= step <= MAX_STEP_MS
            or report["peak_rss_kib"] == 0
            or report["peak_rss_kib"] > MAX_OWNER_RSS_KIB):
        reasons.append("resource_budget")
    return {
        "schema": "live-infinita-nov-operational-canary-gate/v1",
        "status": "pass" if not reasons else "blocked",
        "reasons": sorted(set(reasons)),
        "cycles": report["cycles"],
        "samples": report["samples"],
        "ready_reads": report["ready_reads"],
        "abstentions": report["abstentions"],
        "submissions": report["submissions"],
        "ready_fraction": report.get("ready_fraction"),
        "longest_not_ready_streak": report["longest_not_ready_streak"],
        "frame_tick_advances": report["frame_tick_advances"],
        "frame_tick_regressions": report["frame_tick_regressions"],
        "peak_rss_kib": report["peak_rss_kib"],
        "max_step_ms": step,
        "historical_snapshot_only": True,
        "main_runtime_wired": False,
        "selection_authority": False,
    }


def load_redacted_report(path: Path) -> dict[str, Any]:
    """Strict, bounded parsing of the operator-only 0600 aggregate log."""
    if path.is_symlink() or not path.is_file():
        raise ValueError("log_unavailable")
    file_stat = path.stat()
    if (file_stat.st_size > MAX_LOG_BYTES
            or file_stat.st_size == 0
            or stat.S_IMODE(file_stat.st_mode) & 0o077):
        raise ValueError("log_permissions_or_budget")
    text = path.read_text(encoding="utf-8")
    marker = "MVP018L_OWNER_CANARY_OK "
    matches = [line[len(marker):] for line in text.splitlines()
               if line.startswith(marker)]
    if len(matches) != 1:
        raise ValueError("canary_marker_invalid")
    obj = json.loads(matches[0])
    if not isinstance(obj, dict):
        raise ValueError("canary_aggregate_invalid")
    return obj


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = load_redacted_report(args.log)
        result = evaluate_operational(report)
    except (OSError, ValueError, UnicodeError, json.JSONDecodeError):
        result = {"status": "blocked", "reasons": ["redacted_report_invalid"]}
    label = ("MVP018M_OPERATIONAL_GATE_OK" if result["status"] == "pass"
             else "MVP018M_OPERATIONAL_GATE_BLOCKED")
    print(label + " " + json.dumps(
        result, sort_keys=True, separators=(",", ":"),
    ), flush=True)
    if result["status"] != "pass":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
