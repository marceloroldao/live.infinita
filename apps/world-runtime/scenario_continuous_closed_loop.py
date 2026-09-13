from __future__ import annotations

from copy import deepcopy


def build_continuous_world() -> dict:
    """World fixture for a multi-tick closed-loop V2 run.

    The world owns which action rules are valid and which concrete consequence occurs.
    The rule's possible consequences stay fixed, while the concrete consequence changes
    after tick 12 to create an explicit regime shift that the cognitive engine must
    observe rather than receive as a semantic label.
    """
    return {
        "world_id": "world_continuous_v2",
        "current_tick": 10,
        "current_version": 10,
        "entities": {
            "nova": {
                "entity_id": "nova",
                "status": "active",
                "components": {"transform": {"region_id": "r1"}},
            }
        },
        "relations": {},
        "rules": {
            "actions": [
                {
                    "rule_id": "probe",
                    "actor": "nova",
                    "action": "probe",
                    "target": None,
                    "possible_consequence_addresses": ["live:effect:x", "live:effect:y"],
                    "consequence_address": "live:effect:x",
                },
                {
                    "rule_id": "wait",
                    "actor": "nova",
                    "action": "wait",
                    "target": None,
                    "possible_consequence_addresses": ["live:outcome:no-structural-change"],
                    "consequence_address": "live:outcome:no-structural-change",
                },
            ]
        },
        "events": {},
        "deltas": {},
        "versions": {"10": {"parent_version": 9, "delta_id": None}},
    }


def apply_regime_shift(world: dict) -> dict:
    """Return a new world where the same probe action now concretely yields Y.

    This mutates the world's rule configuration, not the cognitive state. It is the
    external change the V2 must detect from observations.
    """
    shifted = deepcopy(world)
    for rule in shifted["rules"]["actions"]:
        if rule["rule_id"] == "probe":
            rule["consequence_address"] = "live:effect:y"
            break
    return shifted
