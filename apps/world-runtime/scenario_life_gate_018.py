from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_017 import build_life_gate_017_world


_ALLOWED_WIND = {"w_gust_a", "w_lull_a"}
_ALLOWED_CONTEXT = {"b_clear", "b_blocked"}


def build_life_gate_018_world(
    *,
    episode_id: int = 0,
    wind_phase_id: str = "w_gust_a",
    barrier_phase_id: str = "b_clear",
) -> dict:
    """Build one physically admissible state combination for the XOR stress test."""
    if wind_phase_id not in _ALLOWED_WIND:
        raise ValueError("unsupported Gate 018 wind_phase_id")
    if barrier_phase_id not in _ALLOWED_CONTEXT:
        raise ValueError("unsupported Gate 018 barrier_phase_id")

    world = deepcopy(build_life_gate_017_world(episode_id=episode_id))
    world["world_id"] = (
        f"life-gate-018-{wind_phase_id}-{barrier_phase_id}-episode-{episode_id}"
    )

    wind_state = world["entities"]["wind_01"]["components"]["environmental_state"]
    wind_state["phase_id"] = wind_phase_id
    wind_state["generation"] = 0
    wind_state["last_transition_tick"] = int(world["current_tick"])
    wind_state.pop("last_action_id", None)

    barrier_state = world["entities"]["barrier_01"]["components"]["process_state"]
    barrier_state["phase_id"] = barrier_phase_id
    barrier_state["generation"] = 0
    barrier_state["last_transition_tick"] = int(world["current_tick"])
    barrier_state.pop("last_action_id", None)

    world["rules"]["environmental_state_interactions"] = [
        {
            "rule_id": "spring_channel_two_state_interaction",
            "inputs": [
                {
                    "input_id": "i0",
                    "entity": "wind_01",
                    "component": "environmental_state",
                    "field": "phase_id",
                },
                {
                    "input_id": "i1",
                    "entity": "barrier_01",
                    "component": "process_state",
                    "field": "phase_id",
                },
            ],
            "cases": [
                {
                    "case_id": "case_00",
                    "when": {
                        "i0": "w_gust_a",
                        "i1": "b_clear",
                    },
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ],
                },
                {
                    "case_id": "case_01",
                    "when": {
                        "i0": "w_gust_a",
                        "i1": "b_blocked",
                    },
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ],
                },
                {
                    "case_id": "case_10",
                    "when": {
                        "i0": "w_lull_a",
                        "i1": "b_clear",
                    },
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": False,
                        }
                    ],
                },
                {
                    "case_id": "case_11",
                    "when": {
                        "i0": "w_lull_a",
                        "i1": "b_blocked",
                    },
                    "route_overrides": [
                        {
                            "region_id": "spring",
                            "route_id": "spring_channel",
                            "available": True,
                        }
                    ],
                },
            ],
        }
    ]

    # Pairwise evidence is intentionally required to be highly reliable. The gate is
    # meant to show whether any single opaque antecedent can represent the outcome.
    world["rules"]["temporal_evidence_selector"][
        "min_directional_reliability"
    ] = 0.75
    world["rules"]["reality_slice_window"]["frame_count"] = 4
    return world


def initial_nov_needs_018(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
