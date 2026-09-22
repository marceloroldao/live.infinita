from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_009 import build_life_gate_009_world


def build_server_cognitive_rc1_world(*, episode_id: int = 1) -> dict:
    """Server Cognitive RC1 world profile.

    Reuses the validated living-world baseline (Nov + distributed Water +
    synchronized multimodal sensors) and enables the structural policies that were
    validated through Life Gate 028. The profile contains no TikTok, LLM or renderer
    authority.
    """
    world = deepcopy(build_life_gate_009_world(episode_id=episode_id))
    world["world_id"] = f"server-cognitive-rc1-{episode_id}"

    world["rules"]["higher_order_context_selector"] = {
        "min_repetitions": 3,
        "min_independent_slices": 3,
        "min_rho": 0.39,
        "min_context_reliability": 0.75,
        "max_lower_order_reliability": 0.75,
        "context_span": 0.15,
        "max_consequence_delay": 1.5,
        "min_pattern_support": 2,
        "forgetting_lambda0": 0.025,
        "forgetting_consolidation": 1.0,
        "active_evidence_slice_window": 0,
        "active_evidence_time_window": 25.0,
    }
    world["rules"]["reality_slice_event_time"] = {
        "allowed_lateness": 1.0,
        "late_policy": "reject-audit",
        "order_key": ("t_end", "t_start", "slice_id"),
    }
    world["rules"]["server_cognitive_rc1"] = {
        "observer_id": "nova",
        "sensor_frames_per_cycle": 3,
        "environment_ticks_between_frames": 1,
        "simulation_time_step": 1.0,
        "profile_version": "rc1",
    }
    return world


def initial_server_cognitive_rc1_needs(world: dict) -> NeedState:
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "recover": 0,
            "roam": 4,
        },
    )
