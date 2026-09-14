from __future__ import annotations

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from world_tick import WorldTickRunner


class TickLeaseBusy(RuntimeError):
    pass


class SingleWriterTickLease:
    """Host-local exclusive lease for the authoritative world tick writer.

    The lock file is persistent for observability, but ownership is enforced by
    the kernel with flock(). A crashed process automatically releases ownership.
    """

    def __init__(self, path: Path, owner_id: str | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.owner_id = owner_id or f"pid-{os.getpid()}"
        self._fh = None

    def acquire(self) -> bool:
        if self._fh is not None:
            return True
        fh = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({
            "owner_id": self.owner_id,
            "pid": os.getpid(),
            "acquired_at_unix": time.time(),
        }, sort_keys=True, separators=(",", ":")))
        fh.flush()
        os.fsync(fh.fileno())
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None

    def __enter__(self) -> "SingleWriterTickLease":
        if not self.acquire():
            raise TickLeaseBusy(f"world tick lease busy: {self.path}")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()


class WorldTickDriver:
    """Drive logical ticks from wall time without replaying downtime.

    Wall time only determines when the next logical tick is attempted. The
    logical clock itself remains authoritative. If the process is stopped for
    any duration, restart schedules exactly the next tick; there is no catch-up.
    """

    def __init__(
        self,
        runner: WorldTickRunner,
        *,
        lease: SingleWriterTickLease,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.runner = runner
        self.lease = lease
        self.monotonic = monotonic
        self.sleeper = sleeper

    @property
    def interval_seconds(self) -> float:
        return max(0.001, self.runner.clock.state().tick_duration_ms / 1000.0)

    def run_once(self) -> dict[str, Any]:
        if not self.lease.acquire():
            return {"executed": False, "reason": "lease_busy", "tick": None}
        try:
            result = self.runner.tick()
            return {"executed": True, "reason": None, "tick": result}
        finally:
            self.lease.release()

    def serve(self, *, max_ticks: int | None = None) -> list[dict[str, Any]]:
        """Run a cadence loop. Intended for an explicit dedicated process only.

        No elapsed-time accumulation is used: each iteration schedules one next
        logical tick from the current moment. Therefore downtime never creates a
        backlog of missed logical ticks.
        """
        results: list[dict[str, Any]] = []
        count = 0
        while max_ticks is None or count < max_ticks:
            started = self.monotonic()
            results.append(self.run_once())
            count += 1
            elapsed = max(0.0, self.monotonic() - started)
            self.sleeper(max(0.0, self.interval_seconds - elapsed))
        return results
