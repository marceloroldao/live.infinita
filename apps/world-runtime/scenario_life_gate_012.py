from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_009 import build_life_gate_009_world


def build_life_gate_012_world(*, episode_id: int = 0) -> dict:
    """Enable one-tick physical future preview owned by the World Runtime."""
    world = deepcopy(build_life_gate_009_world(episode_id=episode_id))
    world["world_id"] = f"life-gate-012-episode-{episode_id}"
    world["rules"]["environmental_future_preview"] = {
        "runtime": "distributed_environmental",
        "lookahead_ticks": 1,
    }
    return world


def initial_nov_needs_012(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
