"""MVP-018L — continuous, owner-only, read-only current-frame preparation.

This is a standalone bounded observer. No socket, shared-cache file, IPC,
provider injection, action authority or service activation is done here.
The worker's private V2 index stays in memory of the service account.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
import json
import resource
import statistics
from pathlib import Path
import signal
import time
from time import perf_counter
from typing import Any, Callable

from nov_memory_async_prepare import OwnerAsyncDualLanePreparation
from nov_memory_current_frame import sample_current_nov_frame
from nov_memory_recall_cache import VersionedNovRecallCache
from nov_memory_recall_shadow import RecallBlocked

PRIVATE_ROOT = Path("/var/lib/live-infinita/memoria-local")
WORLD_ROOT = Path("/var/lib/live-infinita/autonomous-world")
SOURCE = PRIVATE_ROOT / "external-episodes-incremental" / "external-episodes.sqlite3"
CHECKPOINT = PRIVATE_ROOT / "nov-ingest.checkpoint.json"
WORLD = WORLD_ROOT / "world.json"
COLD = WORLD_ROOT / "cold-store"
LOCK = WORLD_ROOT / "world-mutation.lock"
SCHEMA = "live-infinita-nov-owner-continuous/v1"
PUBLIC_STATUSES = frozenset((
    "ready", "pending", "frame_unavailable", "context_rejected",
    "submission_blocked", "not_started", "not_ready", "blocked",
    "source_changed", "expired", "world_changed", "frame_regressed",
    "frame_lagged", "query_changed", "closed", "unavailable",
))
MAX_FINITE_CYCLES = 60
LATENCY_WINDOW = 256
PHASES = ("sampler", "peek", "submit")


class ContinuousOwnerMonitor:
    """Latest observed Nov frame wins; bounded refresh, never a world writer."""

    def __init__(
        self, worker: Any, sampler: Callable[[], Any], *,
        clock: Callable[[], float] = time.monotonic,
        refresh_seconds: float = 4.0,
        pending_timeout_seconds: float = 8.0,
    ) -> None:
        if (type(refresh_seconds) not in (int, float)
                or not 2 <= refresh_seconds <= 15):
            raise RecallBlocked("continuous_refresh_budget")
        if (type(pending_timeout_seconds) not in (int, float)
                or not 5 <= pending_timeout_seconds <= 20):
            raise RecallBlocked("continuous_pending_budget")
        self.worker = worker
        self.sampler = sampler
        self.clock = clock
        self.refresh_seconds = refresh_seconds
        self.pending_timeout_seconds = pending_timeout_seconds
        self.last_submit: float | None = None
        self.pending_since: float | None = None
        self.samples = 0
        self.ready_reads = 0
        self.abstentions = 0
        self.submissions = 0
        self.status_counts: Counter[str] = Counter()
        self.current_not_ready_streak = 0
        self.longest_not_ready_streak = 0
        self.last_observed_tick: int | None = None
        self.frame_tick_advances = 0
        self.frame_tick_regressions = 0
        self.last_step_phase_ms: dict[str, float] = {name: 0.0 for name in PHASES}
        self.max_phase_ms: dict[str, float] = {name: 0.0 for name in PHASES}

    def _record_phase(self, name: str, started: float) -> None:
        elapsed_ms = (perf_counter() - started) * 1000
        self.last_step_phase_ms[name] = elapsed_ms
        self.max_phase_ms[name] = max(self.max_phase_ms[name], elapsed_ms)

    def step(self) -> dict[str, Any]:
        """One bounded observational iteration; no calls into world authority."""
        self.samples += 1
        self.last_step_phase_ms = {name: 0.0 for name in PHASES}
        phase_started = perf_counter()
        try:
            frame = self.sampler()
        except (RecallBlocked, ValueError, OSError, BlockingIOError):
            self._record_phase("sampler", phase_started)
            self.abstentions += 1
            return self._public("frame_unavailable", queued=False)
        self._record_phase("sampler", phase_started)
        if type(frame.tick_id) is not int or frame.tick_id < 0:
            self.abstentions += 1
            return self._public("frame_unavailable", queued=False)
        if self.last_observed_tick is not None:
            if frame.tick_id > self.last_observed_tick:
                self.frame_tick_advances += 1
            elif frame.tick_id < self.last_observed_tick:
                self.frame_tick_regressions += 1
        self.last_observed_tick = frame.tick_id
        now = self.clock()
        phase_started = perf_counter()
        try:
            view = self.worker.peek(frame)
        except (RecallBlocked, ValueError):
            self._record_phase("peek", phase_started)
            self.abstentions += 1
            return self._public("context_rejected", queued=False)
        self._record_phase("peek", phase_started)
        if view.status == "ready":
            self.pending_since = None
        elif (self.pending_since is not None
              and now - self.pending_since >= self.pending_timeout_seconds):
            # Coalesce/retry; old generation cannot publish over newer.
            self.pending_since = None
        should_refresh = (
            self.pending_since is None
            and (
                self.last_submit is None
                or now - self.last_submit >= self.refresh_seconds
                or view.status not in ("ready", "pending")
            )
        )
        queued = False
        if should_refresh:
            phase_started = perf_counter()
            try:
                self.worker.submit(frame)
            except (RecallBlocked, ValueError):
                self._record_phase("submit", phase_started)
                self.abstentions += 1
                return self._public("submission_blocked", queued=False)
            self._record_phase("submit", phase_started)
            self.last_submit = now
            self.pending_since = now
            self.submissions += 1
            queued = True
            # Mark in-flight rather than claiming the old context is current.
            status = "pending"
        else:
            status = view.status
        if status == "ready":
            self.ready_reads += 1
        else:
            self.abstentions += 1
        return self._public(status, queued=queued, view=view if status == "ready" else None)

    def _public(self, status: str, *, queued: bool,
                view: Any | None = None) -> dict[str, Any]:
        # No untrusted exception/status/body is ever printed to the journal.
        status = status if status in PUBLIC_STATUSES else "context_rejected"
        self.status_counts[status] += 1
        if status == "ready":
            self.current_not_ready_streak = 0
        else:
            self.current_not_ready_streak += 1
            self.longest_not_ready_streak = max(
                self.longest_not_ready_streak, self.current_not_ready_streak,
            )
        summary = {
            "schema": SCHEMA,
            "status": status,
            "submitted": queued,
            "samples": self.samples,
            "ready_reads": self.ready_reads,
            "abstentions": self.abstentions,
            "submissions": self.submissions,
            "historical_snapshot_only": True,
            "live_caught_up_claim": False,
            "selection_authority": False,
            "supplementary_used_to_rank_primary": False,
            "world_mutated": False,
            "central_sync": False,
            "bdr_used": False,
        }
        if view is not None and status == "ready":
            summary["primary_count"] = view.public["primary_count"]
            summary["supplementary_count"] = view.public["supplementary_count"]
            summary["primary_overlap_counts"] = list(view.public["primary_overlap_counts"])
            summary["supplementary_overlap_counts"] = list(
                view.public["supplementary_overlap_counts"]
            )
        return summary


def run(*, cycles: int | None = None, period: float = 2.0,
        refresh: float = 4.0, canary: bool = False,
        emit: Callable[[dict[str, Any]], None] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        sampler: Callable[[], Any] | None = None,
        worker: Any | None = None) -> dict[str, Any]:
    """The bounded canary waits ONLY inside this separate owner process."""
    if (type(period) not in (int, float) or not 0.5 <= period <= 10
            or cycles is not None and (
                type(cycles) is not int or not 2 <= cycles <= MAX_FINITE_CYCLES
            )):
        raise RecallBlocked("continuous_run_budget")
    if canary and cycles is None:
        raise RecallBlocked("continuous_canary_requires_cycle_budget")
    output = emit or (lambda row: print(
        "MVP018L_OWNER_STATUS " + json.dumps(
            row, sort_keys=True, separators=(",", ":"),
        ), flush=True
    ))
    observe = sampler or (lambda: sample_current_nov_frame(
        world_path=WORLD, cold_root=COLD, mutation_lock=LOCK,
    ))
    prepared = worker or OwnerAsyncDualLanePreparation(
        VersionedNovRecallCache(
            source=SOURCE, world_path=WORLD,
            checkpoint_path=CHECKPOINT, private_root=PRIVATE_ROOT,
        ),
    )
    runner = ContinuousOwnerMonitor(
        prepared, observe, clock=clock, refresh_seconds=refresh,
    )
    stop = False

    def request_stop(_signum: int, _frame: Any) -> None:
        nonlocal stop
        stop = True

    original_term = original_int = None
    if worker is None:
        original_term = signal.signal(signal.SIGTERM, request_stop)
        original_int = signal.signal(signal.SIGINT, request_stop)
    prepared.start()
    start_at = clock()
    # Bounded for an eventual long-lived owner process. In the finite
    # 60-cycle canary this retains EVERY primary and follow-up step.
    step_times_ms: deque[float] = deque(maxlen=LATENCY_WINDOW)
    max_step_ms = 0.0
    slow_step_gt_250_count = 0
    slow_step_gt_500_count = 0
    worst_step_phase_ms = {**{name: 0.0 for name in PHASES}, "unattributed": 0.0}

    def timed_step() -> dict[str, Any]:
        nonlocal max_step_ms, slow_step_gt_250_count, slow_step_gt_500_count
        step_started = perf_counter()
        row = runner.step()
        elapsed = (perf_counter() - step_started) * 1000
        step_times_ms.append(elapsed)
        slow_step_gt_250_count += int(elapsed > 250.0)
        slow_step_gt_500_count += int(elapsed > 500.0)
        if elapsed > max_step_ms:
            max_step_ms = elapsed
            for name in PHASES:
                worst_step_phase_ms[name] = runner.last_step_phase_ms[name]
            worst_step_phase_ms["unattributed"] = max(
                0.0, elapsed - sum(runner.last_step_phase_ms.values()),
            )
        return row

    try:
        count = 0
        while not stop and (cycles is None or count < cycles):
            row = timed_step()
            if canary and row["status"] == "pending":
                # Allowed to wait for the service account's background worker
                # here; production's 500-ms world loop is never involved.
                try:
                    frame = observe()
                    ready = prepared.wait_ready(frame, timeout=5.0)
                    if ready.status == "ready":
                        row = timed_step()
                    else:
                        row["status"] = ready.status
                except (RecallBlocked, ValueError, OSError):
                    row["status"] = "frame_unavailable"
            output(row)
            count += 1
            if not stop and (cycles is None or count < cycles):
                # A fixed multiple of the 500-ms world tick can repeatedly
                # collide with the same writer phase. Shift only the probe's
                # next read; never delay the authoritative writer.
                sleep(period * 0.67 if row["status"] == "frame_unavailable" else period)
        aggregate = {
            "schema": SCHEMA,
            "status": "ok" if runner.ready_reads else "no_ready_observations",
            "samples": runner.samples,
            "ready_reads": runner.ready_reads,
            "abstentions": runner.abstentions,
            "submissions": runner.submissions,
            "cycles": count,
            "status_counts": dict(sorted(runner.status_counts.items())),
            "longest_not_ready_streak": runner.longest_not_ready_streak,
            "frame_tick_advances": runner.frame_tick_advances,
            "frame_tick_regressions": runner.frame_tick_regressions,
            "ready_fraction": round(runner.ready_reads / runner.samples, 4)
            if runner.samples else 0.0,
            "max_step_ms": round(max_step_ms, 3),
            "median_step_ms": round(statistics.median(step_times_ms), 3)
            if step_times_ms else 0.0,
            "latency_window_samples": len(step_times_ms),
            "slow_step_gt_250_count": slow_step_gt_250_count,
            "slow_step_gt_500_count": slow_step_gt_500_count,
            "phase_max_ms": {
                name: round(runner.max_phase_ms[name], 3) for name in PHASES
            },
            "worst_step_phase_ms": {
                name: round(value, 3) for name, value in worst_step_phase_ms.items()
            },
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "elapsed_seconds": round(max(0.0, clock() - start_at), 3),
            "historical_snapshot_only": True,
            "live_caught_up_claim": False,
            "main_runtime_wired": False,
            "selection_authority": False,
            "world_mutated": False,
            "central_sync": False,
            "bdr_used": False,
        }
        return aggregate
    finally:
        prepared.close()
        if worker is None:
            signal.signal(signal.SIGTERM, original_term)
            signal.signal(signal.SIGINT, original_int)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--period", type=float, default=2.0)
    parser.add_argument("--refresh", type=float, default=4.0)
    parser.add_argument("--cycles", type=int)
    parser.add_argument("--canary", action="store_true")
    args = parser.parse_args()
    try:
        report = run(
            cycles=args.cycles, period=args.period,
            refresh=args.refresh, canary=args.canary,
        )
    except (RecallBlocked, OSError, ValueError) as exc:
        raise SystemExit("MVP018L_OWNER_BLOCKED " + type(exc).__name__) from exc
    label = "MVP018L_OWNER_CANARY_OK" if args.canary and report["ready_reads"] else (
        "MVP018L_OWNER_CANARY_BLOCKED" if args.canary else "MVP018L_OWNER_STOPPED"
    )
    print(label + " " + json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    if args.canary and not report["ready_reads"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
