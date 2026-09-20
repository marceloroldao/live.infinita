from __future__ import annotations

from copy import deepcopy

from nov_need_scheduler import NeedState, make_need_state
from scenario_life_gate_001 import build_life_gate_world


def build_life_gate_002_world() -> dict:
    """Extend Life Gate 001 with two deterministic need-service actions."""
    world = deepcopy(build_life_gate_world())
    world["world_id"] = "life-gate-002"

    actions = world["rules"]["actions"]
    for rule in actions:
        if rule["rule_id"] == "probe_source":
            rule["need_affordances"] = ["explore"]
        elif rule["rule_id"] == "continue_path":
            rule["action"] = "walk"
            rule["possible_consequence_addresses"] = ["live:outcome:path-progress"]
            rule["consequence_address"] = "live:outcome:path-progress"
            rule["need_affordances"] = ["roam"]

    actions.append(
        {
            "rule_id": "rest_here",
            "actor": "nova",
            "action": "rest",
            "target": None,
            "possible_consequence_addresses": ["live:outcome:rested"],
            "consequence_address": "live:outcome:rested",
            "need_affordances": ["recover"],
        }
    )
    return world


def initial_nov_needs(world: dict) -> NeedState:
    """Initial local pressures for the gate.

    The slight roam lead is an initial agent condition, not knowledge about the
    source. All pressures then grow uniformly with logical time.
    """
    return make_need_state(
        tick_id=int(world["current_tick"]),
        pressures={
            "explore": 0,
            "recover": 0,
            "roam": 4,
        },
    )
