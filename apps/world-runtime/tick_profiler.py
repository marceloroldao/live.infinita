from __future__ import annotations

import json
import math
import os
from collections import deque
from pathlib import Path
from typing import Any


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


class WorldTickProfiler:
    """Opt-in, bounded, non-authoritative per-tick latency measurements.

    No payloads, identities, decisions or memory content are stored. The output
    is a replaceable aggregate, never an append-only log.
    """

    def __init__(
        self, path: Path, *, window: int = 256, report_every: int = 32
    ) -> None:
        if window < 1 or report_every < 1:
            raise ValueError("window and report_every must be positive")
        self.path = Path(path)
        self.samples: deque[dict[str, Any]] = deque(maxlen=window)
        self.report_every = report_every
        self.stages: dict[str, float] = {}
        self.seen = 0

    def observe_stage(self, name: str, duration_ns: int) -> None:
        # Multiple plans may execute under the same stage name in one tick.
        self.stages[name] = self.stages.get(name, 0.0) + max(0, duration_ns) / 1_000_000

    def observe_tick(self, result: dict[str, Any]) -> None:
        elapsed_ms = max(0.0, float(result["elapsed_seconds"]) * 1000)
        interval_ms = max(0.0, float(result["interval_seconds"]) * 1000)
        stage_ms = self.stages
        self.stages = {}
        if not result.get("executed"):
            return
        # Uninstrumented and observer overhead is intentionally visible.
        self.samples.append({
            "elapsed_ms": elapsed_ms,
            "interval_ms": interval_ms,
            "over_budget": elapsed_ms > interval_ms,
            "stages": stage_ms,
            "unaccounted_ms": max(0.0, elapsed_ms - sum(stage_ms.values())),
        })
        self.seen += 1
        if self.seen % self.report_every == 0:
            self.flush()

    @staticmethod
    def _stats(values: list[float]) -> dict[str, float]:
        if not values:
            return {"p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "max_ms": 0.0}
        return {
            "p50_ms": round(_percentile(values, 0.50), 3),
            "p95_ms": round(_percentile(values, 0.95), 3),
            "p99_ms": round(_percentile(values, 0.99), 3),
            "max_ms": round(max(values), 3),
        }

    def snapshot(self) -> dict[str, Any]:
        samples = list(self.samples)
        stage_names = sorted({name for sample in samples for name in sample["stages"]})
        stages = {
            name: {
                "observed_ticks": sum(name in row["stages"] for row in samples),
                **self._stats([row["stages"].get(name, 0.0) for row in samples]),
            }
            for name in stage_names
        }
        over_budget = sum(bool(row["over_budget"]) for row in samples)
        return {
            "profile_schema": "world_tick_profile_v1",
            "window_samples": len(samples),
            "total_observed_ticks": self.seen,
            "tick_budget_ms": round(samples[-1]["interval_ms"], 3) if samples else None,
            "over_budget_ticks": over_budget,
            "over_budget_ratio": round(over_budget / len(samples), 4) if samples else 0.0,
            "total": self._stats([row["elapsed_ms"] for row in samples]),
            "unaccounted": self._stats([row["unaccounted_ms"] for row in samples]),
            "stages": stages,
        }

    def flush(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(self.path.name + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8") as fh:
                json.dump(self.snapshot(), fh, sort_keys=True, ensure_ascii=False)
                fh.write("\n")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
