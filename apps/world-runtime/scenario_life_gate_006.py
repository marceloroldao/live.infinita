from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_005 import build_life_gate_005_world


def build_life_gate_006_world() -> dict:
    """Add indirect noisy/persistent local Water sensing for Nov."""
    world = deepcopy(build_life_gate_005_world())
    world["world_id"] = "life-gate-006"
    world["rules"]["environmental_sensors"] = [
        {
            "sensor_id": "water_local_level",
            "observer": "nova",
            "target": "water_01",
            "source_component": "environmental_distribution",
            "noise_amplitude": 2,
            "hysteresis": 3,
            "persistence_samples": 2,
            "bands": [
                {"band_id": "q0", "min_value": 0},
                {"band_id": "q1", "min_value": 15},
                {"band_id": "q2", "min_value": 35},
            ],
        }
    ]
    return world


def initial_nov_needs_006(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
