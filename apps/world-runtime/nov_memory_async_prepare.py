"""MVP-018K: explicitly started, bounded off-tick memory preparation.

Only the owner process may instantiate this worker. Genuine V2 validation and
SQLite/WAL/checkpoint version probes run on its background thread. The reader
does no filesystem/network access, waits, V2 rehydration, or world mutation.
Its evidence describes a bounded historical snapshot, NEVER live catch-up.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import sqlite3
from threading import Condition, Thread
from time import monotonic
from typing import Any, Callable

from memoria_v2_adapter import CognitiveFrame
from nov_memory_context_shadow import MemoryShadowContext, freeze_memory_context
from nov_memory_dual_lane_shadow import OwnerDualLaneRecallObserver
from nov_memory_recall_cache import VersionedNovRecallCache, frame_query, frame_world
from nov_memory_recall_shadow import RecallBlocked

SCHEMA = "live-infinita-nov-async-dual-lane/v1"
MAX_AGE_SECONDS = 6.0
MAX_FRAME_LAG_TICKS = 20
WATCH_INTERVAL_SECONDS = 0.5


@dataclass(frozen=True, slots=True, repr=False)
class PreparedSnapshot:
    version: Any
    world_id: str
    prepared_tick: int
    seed: dict[str, Any] | None
    query: dict[str, str]
    primary: dict[str, Any]
    supplementary: dict[str, Any]
    metrics: dict[str, Any]
    prepared_at: float


@dataclass(frozen=True, slots=True, repr=False)
class PreparedRead:
    status: str
    primary: MemoryShadowContext | None
    supplementary: MemoryShadowContext | None
    public: dict[str, Any]


@dataclass(slots=True, repr=False)
class OwnerAsyncDualLanePreparation:
    cache: VersionedNovRecallCache = field(repr=False)
    max_age_seconds: float = MAX_AGE_SECONDS
    max_frame_lag_ticks: int = MAX_FRAME_LAG_TICKS
    watch_interval_seconds: float = WATCH_INTERVAL_SECONDS
    _clock: Callable[[], float] = field(default=monotonic, repr=False)
    _observer: Any = field(default=None, repr=False)
    _cv: Condition = field(default_factory=Condition, init=False, repr=False)
    _thread: Thread | None = field(default=None, init=False, repr=False)
    _pending: tuple[int, CognitiveFrame] | None = field(default=None, init=False, repr=False)
    _generation: int = field(default=0, init=False, repr=False)
    _snapshot: PreparedSnapshot | None = field(default=None, init=False, repr=False)
    _state: str = field(default="not_started", init=False)
    _closed: bool = field(default=False, init=False)
    _blocked_reason: str | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if (type(self.max_age_seconds) not in (int, float)
                or not 1.0 <= self.max_age_seconds <= 30.0):
            raise RecallBlocked("async_age_budget")
        if (type(self.max_frame_lag_ticks) is not int
                or not 0 <= self.max_frame_lag_ticks <= 120):
            raise RecallBlocked("async_frame_lag_budget")
        if (type(self.watch_interval_seconds) not in (int, float)
                or not 0.1 <= self.watch_interval_seconds <= 5.0):
            raise RecallBlocked("async_watch_budget")
        if self._observer is None:
            self._observer = OwnerDualLaneRecallObserver(self.cache)

    def start(self) -> None:
        """Explicit opt-in; never called by autonomous_runtime_main."""
        with self._cv:
            if self._closed:
                raise RecallBlocked("async_closed")
            if self._thread is not None:
                raise RecallBlocked("async_already_started")
            self._state = "not_ready"
            self._thread = Thread(target=self._run, name="nov-memory-owner-prepare", daemon=True)
            self._thread.start()

    def submit(self, frame: CognitiveFrame) -> str:
        """Latest request wins; never reads the private source on caller thread."""
        frame_world(frame)
        with self._cv:
            if self._closed or self._thread is None:
                raise RecallBlocked("async_not_running")
            self._generation += 1
            self._pending = (self._generation, deepcopy(frame))
            self._state = "pending"
            self._blocked_reason = None
            self._cv.notify_all()
        return "queued"

    def _run(self) -> None:
        while True:
            with self._cv:
                if self._pending is None and not self._closed:
                    self._cv.wait(timeout=self.watch_interval_seconds)
                if self._closed:
                    return
                request = self._pending
                self._pending = None
                snapshot = self._snapshot
            if request is None:
                if snapshot is not None:
                    try:
                        current = self.cache._current_version()
                    except (OSError, ValueError):
                        current = None
                    if current != snapshot.version:
                        with self._cv:
                            if self._snapshot is snapshot:
                                self._snapshot = None
                                self._state = "source_changed"
                                self._cv.notify_all()
                continue
            generation, frame = request
            try:
                before = self.cache._current_version()
                primary, supplementary, metrics = self._observer.refresh(frame)
                with self.cache._lock:
                    eligible = [row for row in self.cache._validated_index
                                if row["logical_tick"] <= frame.tick_id]
                    seed = max(eligible, key=lambda row: (
                        row["logical_tick"], row["record_key"],
                    )) if eligible else None
                    query = frame_query(frame, seed) if seed is not None else {}
                after = self.cache._current_version()
                if before != after or after.world_id != frame_world(frame):
                    raise RecallBlocked("async_source_moved")
                # Worker publication is atomic: no mutable private payload
                # escapes the owner process or reaches disk.
                prepared = PreparedSnapshot(
                    version=after, world_id=after.world_id,
                    prepared_tick=frame.tick_id,
                    seed={"addresses": deepcopy(seed["addresses"])} if seed is not None else None,
                    query=dict(query), primary=primary,
                    supplementary=supplementary, metrics=dict(metrics),
                    prepared_at=self._clock(),
                )
            except Exception as exc:
                # Only a fixed failure category, never private exception text.
                reason = (
                    "permission_denied" if isinstance(exc, PermissionError)
                    else "sqlite_error" if isinstance(exc, sqlite3.Error)
                    else "verification_blocked" if isinstance(exc, RecallBlocked)
                    else "unexpected_failure"
                )
                with self._cv:
                    if self._generation == generation and not self._closed:
                        self._snapshot = None
                        self._state = "blocked"
                        self._blocked_reason = reason
                        self._cv.notify_all()
                continue
            with self._cv:
                if self._generation == generation and not self._closed:
                    self._snapshot = prepared
                    self._state = "ready"
                    self._blocked_reason = None
                    self._cv.notify_all()

    def peek(self, frame: CognitiveFrame) -> PreparedRead:
        """Non-blocking view; no source version probe or SQLite access."""
        with self._cv:
            snapshot, state, closed = self._snapshot, self._state, self._closed
            reason = self._blocked_reason
        status = "closed" if closed else state
        # A newer frame is in flight: never expose the previous frame as
        # ready while its replacement has not completed.
        if status == "pending":
            return PreparedRead("pending", None, None, {
                "schema": SCHEMA, "status": "pending",
                "historical_snapshot_only": True,
                "live_caught_up_claim": False, "selection_authority": False,
                "world_mutated": False, "bdr_used": False, "central_sync": False,
            })
        age: float | None = None
        if not closed and snapshot is not None:
            age = self._clock() - snapshot.prepared_at
            if age < 0 or age > self.max_age_seconds:
                status = "expired"
            elif frame_world(frame) != snapshot.world_id:
                status = "world_changed"
            elif frame.tick_id < snapshot.prepared_tick:
                status = "frame_regressed"
            elif frame.tick_id - snapshot.prepared_tick > self.max_frame_lag_ticks:
                status = "frame_lagged"
            elif ((frame_query(frame, snapshot.seed) if snapshot.seed else {})
                  != snapshot.query):
                status = "query_changed"
            else:
                status = "ready"
        public = {
            "schema": SCHEMA, "status": status,
            "historical_snapshot_only": True,
            "live_caught_up_claim": False,
            "selection_authority": False,
            "world_mutated": False,
            "bdr_used": False,
            "central_sync": False,
        }
        if status == "blocked" and reason in {
            "permission_denied", "sqlite_error",
            "verification_blocked", "unexpected_failure",
        }:
            public["blocked_reason"] = reason
        if status != "ready" or snapshot is None:
            return PreparedRead(status, None, None, public)
        try:
            primary = freeze_memory_context(frame, snapshot.primary)
            supplementary = freeze_memory_context(frame, snapshot.supplementary)
        except ValueError:
            return PreparedRead("context_rejected", None, None, {
                **public, "status": "context_rejected",
            })
        public.update({
            "snapshot_records": primary.public_view["snapshot_records"],
            "primary_count": primary.public_view["evidence_count"],
            "supplementary_count": supplementary.public_view["evidence_count"],
            "primary_overlap_counts": list(primary.public_view["matched_address_counts"]),
            "supplementary_overlap_counts": list(
                supplementary.public_view["matched_address_counts"]
            ),
            "primary_unchanged": snapshot.metrics["primary_count_unchanged"]
            == primary.public_view["evidence_count"],
            "snapshot_age_ms": round(max(0.0, age or 0) * 1000, 3),
        })
        return PreparedRead("ready", primary, supplementary, public)

    def wait_ready(self, frame: CognitiveFrame, *, timeout: float = 5.0) -> PreparedRead:
        """For OFFLINE operator tests only; never call in the 500-ms world tick."""
        if type(timeout) not in (int, float) or not 0 < timeout <= 10:
            raise RecallBlocked("async_wait_budget")
        deadline = self._clock() + timeout
        while True:
            result = self.peek(frame)
            if result.status == "ready" or result.status in (
                "blocked", "closed", "source_changed", "context_rejected",
            ):
                return result
            left = deadline - self._clock()
            if left <= 0:
                return PreparedRead("timeout", None, None, {
                    **result.public, "status": "timeout",
                })
            with self._cv:
                self._cv.wait(timeout=min(left, 0.05))

    def close(self) -> None:
        with self._cv:
            self._closed = True
            self._pending = None
            self._snapshot = None
            self._state = "closed"
            self._cv.notify_all()
            thread = self._thread
        if thread is not None:
            thread.join(timeout=10.0)
