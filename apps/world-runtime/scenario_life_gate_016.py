from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_015 import build_life_gate_015_world


def build_life_gate_016_world(
    *,
    episode_id: int = 0,
    context_state_id: str = "ctx_clear",
) -> dict:
    """Add a third physical condition that can block the usual a0 -> d1 consequence."""
    if context_state_id not in {"ctx_clear", "ctx_blocked"}:
        raise ValueError("unsupported context_state_id")

    world = deepcopy(
        build_life_gate_015_world(
            episode_id=episode_id,
            wind_phase_id="w_gust_a",
        )
    )
    world["world_id"] = f"life-gate-016-{context_state_id}-episode-{episode_id}"

    world["entities"]["barrier_01"] = {
        "entity_id": "barrier_01",
        "class": "environmental_condition",
        "type": "route_barrier",
        "status": "active",
        "version": int(world["current_version"]),
        "created_at_tick": int(world["current_tick"]),
        "components": {
            "transform": {
                "region_id": "spring",
            },
            "condition_state": {
                "state_id": context_state_id,
            },
        },
    }

    world["rules"]["environmental_route_constraints"] = [
        {
            "rule_id": "spring_channel_barrier",
            "entity": "barrier_01",
            "source_component": "condition_state",
            "source_field": "state_id",
            "states": {
                "ctx_clear": {
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ]
                },
                "ctx_blocked": {
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ]
                },
            },
        }
    ]

    world["rules"]["multimodal_sensors"].append(
        {
            "sensor_id": "s_context_signal_01",
            "observer": "nova",
            "target": "barrier_01",
            "source_component": "condition_state",
            "source_field": "state_id",
            "kind": "component_enum",
            "value_band_ids": {
                "ctx_clear": "c0",
                "ctx_blocked": "c1",
            },
        }
    )

    world["rules"]["reality_slice_window"]["frame_count"] = 4
    world["rules"]["temporal_evidence_selector"][
        "min_directional_reliability"
    ] = 0.75
    return world


def initial_nov_needs_016(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
