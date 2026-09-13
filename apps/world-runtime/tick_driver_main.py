from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from npc_cognitive_stack import NpcCognitiveStack, build_npc_cognitive_stack
from tick_driver import SingleWriterTickLease, WorldTickDriver
from world_tick import WorldTickRunner


def build_autonomous_world_tick(
    *,
    clock: Any,
    scheduler: Any,
    proposal_ledger: Any,
    data_dir: Path,
    npc_ids: list[str],
    world_provider: Any | None = None,
    event_scheduler: Any | None = None,
    conditional_event_scheduler: Any | None = None,
    plan_arbiter: Any | None = None,
    need_threshold: float = 0.70,
    cooldown_ticks: int = 20,
    strategy_min_samples: int = 2,
) -> tuple[WorldTickRunner, NpcCognitiveStack]:
    """Compose, but do not start, the authoritative autonomous NPC runtime.

    Process ownership remains explicit: callers may inspect/test the returned
    runner and only then hand it to ``run_driver`` as the single writer.
    """

    cognition = build_npc_cognitive_stack(
        data_dir=Path(data_dir),
        proposal_ledger=proposal_ledger,
        plan_scheduler=scheduler,
        npc_ids=npc_ids,
        world_provider=world_provider,
        need_threshold=need_threshold,
        cooldown_ticks=cooldown_ticks,
        strategy_min_samples=strategy_min_samples,
    )
    runner = WorldTickRunner(
        clock,
        scheduler,
        event_scheduler=event_scheduler,
        conditional_event_scheduler=conditional_event_scheduler,
        plan_arbiter=plan_arbiter,
        **cognition.world_tick_kwargs(),
    )
    return runner, cognition


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
