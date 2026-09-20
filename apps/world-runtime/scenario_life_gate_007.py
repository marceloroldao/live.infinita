from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_006 import build_life_gate_006_world


def build_life_gate_007_world() -> dict:
    """Add synchronized independent sensor channels for the same environmental reality."""
    world = deepcopy(build_life_gate_006_world())
    world["world_id"] = "life-gate-007"

    # Gate 007 replaces the single scalar sensor with four independent channels.
    world["rules"].pop("environmental_sensors", None)
    world["rules"]["multimodal_sensors"] = [
        {
            "sensor_id": "s_presence",
            "observer": "nova",
            "target": "water_01",
            "source_component": "environmental_distribution",
            "kind": "presence",
            "absent_band_id": "p0",
            "present_band_id": "p1",
        },
        {
            "sensor_id": "s_intensity",
            "observer": "nova",
            "target": "water_01",
            "source_component": "environmental_distribution",
            "kind": "intensity",
            "bands": [
                {"band_id": "i0", "min_value": 0},
                {"band_id": "i1", "min_value": 15},
                {"band_id": "i2", "min_value": 35},
            ],
        },
        {
            "sensor_id": "s_trend",
            "observer": "nova",
            "target": "water_01",
            "source_component": "environmental_distribution",
            "kind": "trend",
            "stable_band_id": "t0",
            "rising_band_id": "t1",
            "falling_band_id": "t2",
            "deadband": 2,
        },
        {
            "sensor_id": "s_flow",
            "observer": "nova",
            "target": "water_01",
            "source_component": "environmental_distribution",
            "kind": "dominant_transfer",
            "none_band_id": "d0",
            "route_band_ids": {
                "spring_channel": "d1",
                "spring_hollow": "d2",
                "channel_basin": "d3",
                "hollow_basin": "d4",
            },
        },
    ]
    return world


def initial_nov_needs_007(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
