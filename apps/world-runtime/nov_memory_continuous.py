"""MVP-018L — continuous, owner-only, read-only current-frame preparation.

This is a standalone bounded observer. No socket, shared-cache file, IPC,
provider injection, action authority or service activation is done here.
The worker's private V2 index stays in memory of the service account.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import time
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

    def step(self) -> dict[str, Any]:
        """One bounded observational iteration; no calls into world authority."""
        self.samples += 1
        try:
            frame = self.sampler()
        except (RecallBlocked, ValueError, OSError, BlockingIOError):
            self.abstentions += 1
            return self._public("frame_unavailable", queued=False)
        now = self.clock()
        try:
            view = self.worker.peek(frame)
        except (RecallBlocked, ValueError):
            self.abstentions += 1
            return self._public("context_rejected", queued=False)
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
            try:
                self.worker.submit(frame)
            except (RecallBlocked, ValueError):
                self.abstentions += 1
                return self._public("submission_blocked", queued=False)
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
            or cycles is not None and (type(cycles) is not int or not 2 <= cycles <= 12)):
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
    try:
        count = 0
        while not stop and (cycles is None or count < cycles):
            row = runner.step()
            if canary and row["status"] == "pending":
                # Allowed to wait for the service account's background worker
                # here; production's 500-ms world loop is never involved.
                try:
                    frame = observe()
                    ready = prepared.wait_ready(frame, timeout=5.0)
                    if ready.status == "ready":
                        row = runner.step()
                    else:
                        row["status"] = ready.status
                except (RecallBlocked, ValueError, OSError):
                    row["status"] = "frame_unavailable"
            output(row)
            count += 1
            if not stop and (cycles is None or count < cycles):
                sleep(period)
        aggregate = {
            "schema": SCHEMA,
            "status": "ok" if runner.ready_reads else "no_ready_observations",
            "samples": runner.samples,
            "ready_reads": runner.ready_reads,
            "abstentions": runner.abstentions,
            "submissions": runner.submissions,
            "cycles": count,
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
