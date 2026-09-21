from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_007 import build_life_gate_007_world


def build_life_gate_008_world(*, episode_id: int = 0) -> dict:
    """Add a world-owned temporal window policy over synchronized sensor frames."""
    world = deepcopy(build_life_gate_007_world())
    world["world_id"] = f"life-gate-008-episode-{episode_id}"
    world["rules"]["reality_slice_window"] = {
        "frame_count": 3,
        "tick_seconds": 0.10,
        "occurrence_duration": 0.02,
    }
    return world


def initial_nov_needs_008(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
