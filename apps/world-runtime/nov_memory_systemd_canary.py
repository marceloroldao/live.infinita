"""MVP-018O: pure one-shot systemd canary unit and redacted result gate.

The root/operator shell wrapper owns all installation and cleanup. This
module cannot start a service, access private V2 files or change the world.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from nov_memory_release_contract import CORE, PYTHON, render_unit, ReleaseBlocked
from nov_memory_continuous import SCHEMA as OWNER_SCHEMA, PUBLIC_STATUSES

SCHEMA = "live-infinita-nov-ephemeral-systemd-gate/v1"
CYCLES = 60
MIN_READY_READS = 12
MIN_READY_FRACTION = 0.30
MAX_NOT_READY_STREAK = 20
MAX_STEP_MS = 250.0
MAX_RSS_KIB = 384 * 1024
MAX_JOURNAL_BYTES = 64 * 1024
UNIT_MARKER = "MVP018L_OWNER_STOPPED "


def render_canary(template: str, root: Path, *, core: Path = CORE,
                  python: Path = PYTHON) -> str:
    base = render_unit(template, root, core=core, python=python)
    lines = base.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("ExecStart=")]
    restarts = [i for i, line in enumerate(lines) if line.startswith("Restart=")]
    if (len(starts) != 1 or len(restarts) != 1
            or not lines[starts[0]].endswith(" --period 2 --refresh 4 --scratch-root /run/live-infinita-nov-preparer")
            or lines[restarts[0]] != "Restart=on-failure"
            or lines.count("[Install]") != 1):
        raise ReleaseBlocked("canary_template_mismatch")
    lines[starts[0]] += " --cycles " + str(CYCLES)
    lines[restarts[0]] = "Restart=no"
    lines = lines[:lines.index("[Install]")]
    output = "\n".join(lines) + "\n"
    if ("WantedBy=" in output or "Restart=on-failure" in output
            or " --canary" in output or output.count("--cycles") != 1):
        raise ReleaseBlocked("canary_install_contract")
    return output


def evaluate_journal(text: str) -> dict[str, Any]:
    """Only aggregate status enters the public response. No arbitrary log text."""
    def blocked(code: str) -> dict[str, Any]:
        return {"schema": SCHEMA, "status": "blocked", "reasons": [code]}

    if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_JOURNAL_BYTES:
        return blocked("journal_budget")
    selected = [line.removeprefix(UNIT_MARKER) for line in text.splitlines()
                if line.startswith(UNIT_MARKER)]
    if len(selected) != 1:
        return blocked("aggregate_marker")
    try:
        r = json.loads(selected[0])
    except ValueError:
        return blocked("aggregate_json")
    if not isinstance(r, dict) or r.get("schema") != OWNER_SCHEMA:
        return blocked("aggregate_schema")
    flags = {
        "historical_snapshot_only": True, "live_caught_up_claim": False,
        "main_runtime_wired": False, "selection_authority": False,
        "world_mutated": False, "central_sync": False, "bdr_used": False,
    }
    if any(r.get(key) is not expected for key, expected in flags.items()):
        return blocked("authority_contract")
    keys = ("cycles", "samples", "ready_reads", "abstentions",
            "submissions", "frame_tick_advances", "frame_tick_regressions",
            "peak_rss_kib", "longest_not_ready_streak", "slow_step_gt_250_count",
            "slow_step_gt_500_count")
    if any(type(r.get(key)) is not int or r[key] < 0 for key in keys):
        return blocked("aggregate_metrics")
    counts = r.get("status_counts")
    if (r.get("status") != "ok" or r["cycles"] != CYCLES
            or r["samples"] < CYCLES
            or r["ready_reads"] + r["abstentions"] != r["samples"]
            or r["ready_reads"] < MIN_READY_READS
            or r["ready_reads"] / r["samples"] < MIN_READY_FRACTION
            or r["longest_not_ready_streak"] > MAX_NOT_READY_STREAK
            or r["submissions"] < 1
            or r["frame_tick_advances"] < 5
            or r["frame_tick_regressions"] != 0
            or not isinstance(counts, dict)
            or any(k not in PUBLIC_STATUSES or type(v) is not int or v < 0
                   for k, v in counts.items())
            or sum(counts.values()) != r["samples"]
            or counts.get("ready", 0) != r["ready_reads"]):
        return blocked("readiness_or_accounting")
    step = r.get("max_step_ms")
    if (type(step) not in (int, float) or not math.isfinite(step)
            or not 0 <= step <= MAX_STEP_MS or not 0 < r["peak_rss_kib"] <= MAX_RSS_KIB
            or r["slow_step_gt_250_count"] or r["slow_step_gt_500_count"]):
        return blocked("resource_budget")
    return {
        "schema": SCHEMA, "status": "pass", "reasons": [],
        "cycles": r["cycles"], "samples": r["samples"],
        "ready_reads": r["ready_reads"], "abstentions": r["abstentions"],
        "ready_fraction": round(r["ready_reads"] / r["samples"], 4),
        "longest_not_ready_streak": r["longest_not_ready_streak"],
        "status_counts": dict(sorted(counts.items())),
        "frame_tick_advances": r["frame_tick_advances"],
        "frame_tick_regressions": r["frame_tick_regressions"],
        "max_step_ms": step, "peak_rss_kib": r["peak_rss_kib"],
        "historical_snapshot_only": True, "selection_authority": False,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--unit-out", type=Path, required=True)
    parser.add_argument("--journal", type=Path)
    args = parser.parse_args()
    try:
        if args.journal is None:
            unit = render_canary(args.template.read_text(encoding="utf-8"), args.root)
            if args.unit_out.parent != args.root or args.unit_out.is_symlink():
                raise ReleaseBlocked("output_path")
            args.unit_out.write_text(unit, encoding="utf-8")
            args.unit_out.chmod(0o600)
            print("MVP018O_CANARY_UNIT_READY")
        else:
            if args.journal.is_symlink() or args.journal.stat().st_size > MAX_JOURNAL_BYTES:
                raise ReleaseBlocked("journal_path")
            result = evaluate_journal(args.journal.read_text(encoding="utf-8"))
            label = "MVP018O_CANARY_GATE_OK" if result["status"] == "pass" else "MVP018O_CANARY_GATE_BLOCKED"
            print(label + " " + json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
            if result["status"] != "pass":
                raise SystemExit(2)
    except (OSError, UnicodeError, ReleaseBlocked):
        print("MVP018O_CANARY_GATE_BLOCKED path_or_unit_invalid", flush=True)
        raise SystemExit(2)
