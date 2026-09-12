from __future__ import annotations

import os
from pathlib import Path

from tick_driver import SingleWriterTickLease, WorldTickDriver


def build_driver(world_tick_runner, data_dir: Path, owner_id: str | None = None) -> WorldTickDriver:
    return WorldTickDriver(
        world_tick_runner,
        lease=SingleWriterTickLease(
            data_dir / "world-tick.lock",
            owner_id=owner_id or os.getenv("LIVE_INFINITA_TICK_OWNER") or None,
        ),
    )


def run_driver(world_tick_runner, data_dir: Path) -> None:
    """Explicit process entrypoint helper.

    The runtime does not call this automatically. Deployment must deliberately
    construct the authoritative WorldTickRunner and start this driver as the
    single writer when autonomous simulation is enabled.
    """
    build_driver(world_tick_runner, data_dir).serve()
