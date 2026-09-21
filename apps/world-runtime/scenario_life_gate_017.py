from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_015 import build_life_gate_015_world


def build_life_gate_017_world(*, episode_id: int = 0) -> dict:
    """Add an independently evolving context process with no per-episode context selector."""
    world = deepcopy(
        build_life_gate_015_world(
            episode_id=episode_id,
            wind_phase_id="w_gust_a",
        )
    )
    world["world_id"] = f"life-gate-017-episode-{episode_id}"

    world["entities"]["barrier_01"] = {
        "entity_id": "barrier_01",
        "class": "environmental_process",
        "type": "route_barrier_process",
        "status": "active",
        "version": int(world["current_version"]),
        "created_at_tick": int(world["current_tick"]),
        "components": {
            "transform": {
                "region_id": "spring",
            },
            "process_state": {
                "phase_id": "b_clear",
                "generation": 0,
                "last_transition_tick": int(world["current_tick"]),
            },
        },
    }

    world["rules"]["environmental_context_processes"] = [
        {
            "rule_id": "spring_channel_barrier_cycle",
            "entity": "barrier_01",
            "state_component": "process_state",
            "phase_field": "phase_id",
            "min_ticks": 1,
            "phases": [
                {
                    "phase_id": "b_clear",
                    "action_id": "barrier_allow_channel",
                    "next_phase_id": "b_blocked",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ],
                },
                {
                    "phase_id": "b_blocked",
                    "action_id": "barrier_block_channel",
                    "next_phase_id": "b_clear",
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ],
                },
            ],
        }
    ]

    world["rules"]["multimodal_sensors"].append(
        {
            "sensor_id": "s_context_signal_01",
            "observer": "nova",
            "target": "barrier_01",
            "source_component": "process_state",
            "source_field": "phase_id",
            "kind": "component_enum",
            "value_band_ids": {
                "b_clear": "c0",
                "b_blocked": "c1",
            },
        }
    )

    world["rules"]["reality_slice_window"]["frame_count"] = 4
    world["rules"]["temporal_evidence_selector"][
        "min_directional_reliability"
    ] = 0.75
    return world


def initial_nov_needs_017(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
