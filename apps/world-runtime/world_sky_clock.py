"""Read-only sky timing derived from the persisted simulation clock.
No memory observations or World State writes are performed here.
"""
import json
from pathlib import Path

SCHEMA = "live-infinita-sky-clock/v1"
CYCLE_MS = 3_600_000

def sky_clock(path: Path, world_id: str) -> dict | None:
    try:
        if not world_id or path.is_symlink() or path.stat().st_size > 4096:
            return None
        raw = json.loads(path.read_text())
        if not isinstance(raw, dict) or raw.get("clock_schema") != "simulation_clock_v1":
            return None
        tick, duration, paused = raw.get("tick"), raw.get("tick_duration_ms"), raw.get("paused")
        if type(tick) is not int or not 0 <= tick <= 10**12:
            return None
        if type(duration) is not int or not 1 <= duration <= 60_000 or type(paused) is not bool:
            return None
        return {"schema": SCHEMA, "world_id": world_id, "tick": tick,
                "tick_duration_ms": duration, "paused": paused,
                "logical_time_ms": tick * duration, "cycle_ms": CYCLE_MS,
                "source": "persisted_simulation_clock",
                "memory_linked": False}
    except (OSError, ValueError, TypeError):
        return None
