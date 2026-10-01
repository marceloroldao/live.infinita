from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class SimulationClockState:
    tick: int
    tick_duration_ms: int
    paused: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "clock_schema": "simulation_clock_v1",
            "tick": self.tick,
            "tick_duration_ms": self.tick_duration_ms,
            "paused": self.paused,
            "logical_time_ms": self.tick * self.tick_duration_ms,
        }


class SimulationClock:
    """Persistent logical clock independent from wall time and renderer FPS."""

    def __init__(
        self,
        path: Path,
        *,
        tick_duration_ms: int = 500,
        stage_observer: Callable[[str, int], None] | None = None,
        monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        if tick_duration_ms <= 0:
            raise ValueError("tick_duration_ms must be positive")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stage_observer = stage_observer
        self.monotonic_ns = monotonic_ns
        if self.path.exists():
            state = self._load()
            if int(state.get("tick_duration_ms", 0)) <= 0:
                raise ValueError("invalid persisted clock state")
        else:
            self._save(SimulationClockState(0, tick_duration_ms, False).as_dict())

    def _stage(self, name: str, fn: Callable[[], Any]) -> Any:
        if self.stage_observer is None:
            return fn()
        started = self.monotonic_ns()
        try:
            return fn()
        finally:
            try:
                self.stage_observer(
                    name,
                    max(0, self.monotonic_ns() - started),
                )
            except Exception:
                pass

    def _load(self) -> dict[str, Any]:
        raw = self._stage(
            "clock.storage.read",
            lambda: self.path.read_text(encoding="utf-8"),
        )
        return self._stage(
            "clock.storage.parse",
            lambda: json.loads(raw),
        )

    def _save(self, value: dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        payload = self._stage(
            "clock.storage.serialize",
            lambda: json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            ) + "\n",
        )
        self._stage(
            "clock.storage.write_tmp",
            lambda: tmp.write_text(payload, encoding="utf-8"),
        )
        self._stage(
            "clock.storage.replace",
            lambda: tmp.replace(self.path),
        )

    def state(self) -> SimulationClockState:
        raw = self._load()
        return SimulationClockState(
            tick=int(raw.get("tick", 0)),
            tick_duration_ms=int(raw.get("tick_duration_ms", 500)),
            paused=bool(raw.get("paused", False)),
        )

    def pause(self) -> SimulationClockState:
        state = self.state()
        next_state = SimulationClockState(state.tick, state.tick_duration_ms, True)
        self._save(next_state.as_dict())
        return next_state

    def resume(self) -> SimulationClockState:
        state = self.state()
        next_state = SimulationClockState(state.tick, state.tick_duration_ms, False)
        self._save(next_state.as_dict())
        return next_state

    def set_tick_duration_ms(self, value: int) -> SimulationClockState:
        if value <= 0:
            raise ValueError("tick_duration_ms must be positive")
        state = self.state()
        next_state = SimulationClockState(state.tick, int(value), state.paused)
        self._save(next_state.as_dict())
        return next_state

    def advance(self, *, force: bool = False) -> SimulationClockState:
        state = self.state()
        if state.paused and not force:
            return state
        next_state = SimulationClockState(state.tick + 1, state.tick_duration_ms, state.paused)
        self._save(next_state.as_dict())
        return next_state
