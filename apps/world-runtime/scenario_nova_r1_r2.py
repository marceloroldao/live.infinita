from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass

from memoria_v2_adapter import (
    build_cognitive_frame,
    candidate_from_transition,
    to_memoria_v2_request_payload,
)


@dataclass(frozen=True, slots=True)
class ScenarioStep:
    tick_id: int
    region_id: str
    proposal_id: str
    action: str
    target: str | None
    expected_consequence: str


def _world(region: str, *, tick: int, version: int) -> dict:
    return {
        "current_tick": tick,
        "current_version": version,
        "entities": {
            "nova": {
                "entity_id": "nova",
                "status": "active",
                "components": {"transform": {"region_id": region}},
            },
            "fire": {
                "entity_id": "fire",
                "status": "active",
                "components": {"transform": {"region_id": region}},
            },
        },
        "relations": {
            "rel_001": {
                "relation_id": "rel_001",
                "subject": "nova",
                "predicate": "near",
                "object": "fire",
                "status": "active",
            }
        },
    }


def _proposal(step: ScenarioStep) -> dict:
    return {
        "proposal_id": step.proposal_id,
        "actor": "nova",
        "action": step.action,
        "target": step.target,
        "source": "memoria-v2-gym",
        "tick_id": step.tick_id,
    }


def _after_for(step: ScenarioStep) -> dict:
    after = _world(step.region_id, tick=step.tick_id + 1, version=step.tick_id + 1)
    after["entities"]["nova"].setdefault("components", {})["cognitive_probe"] = {
        "outcome": step.expected_consequence
    }
    return after


def build_scenario_frames() -> tuple[dict, ...]:
    """Build deterministic Live.Infinita frames for an R1->R2->R1 regime scenario.

    This module only validates the Live side of the bridge. It does not emulate the
    Memoria.ia cognitive engine. Each step produces a world-derived payload that can
    be consumed by `make_live_request()` on the V2 side.
    """

    steps = (
        ScenarioStep(1, "r1", "p-r1-a-1", "probe", "fire", "outcome:x"),
        ScenarioStep(2, "r1", "p-r1-a-2", "probe", "fire", "outcome:x"),
        ScenarioStep(3, "r2", "p-r2-a-1", "probe", "fire", "outcome:y"),
        ScenarioStep(4, "r2", "p-r2-a-2", "probe", "fire", "outcome:y"),
        ScenarioStep(5, "r1", "p-r1-a-3", "probe", "fire", "outcome:x"),
    )

    output: list[dict] = []
    for step in steps:
        before = _world(step.region_id, tick=step.tick_id, version=step.tick_id)
        after = _after_for(step)
        # The structural transition uses a stable outcome entity address rather than
        # any semantic interpretation by the cognitive core.
        after["entities"]["effect"] = {
            "entity_id": step.expected_consequence,
            "status": "active",
            "components": {"transform": {"region_id": step.region_id}},
        }
        after["relations"]["rel_effect"] = {
            "relation_id": "rel_effect",
            "subject": "nova",
            "predicate": "observes",
            "object": "effect",
            "status": "active",
        }

        proposal = _proposal(step)
        candidate = candidate_from_transition(
            candidate_id=f"c-{step.proposal_id}",
            proposal_id=step.proposal_id,
            before=before,
            after=after,
            observer_id="nova",
            event_ids=(f"e-{step.tick_id}",),
        )
        frame = build_cognitive_frame(
            world=before,
            observer_id="nova",
            proposals=(proposal,),
            candidates=(candidate,),
            event_ids=(f"e-{step.tick_id}",),
        )
        output.append(to_memoria_v2_request_payload(frame, proposal_id=step.proposal_id))

    return tuple(output)


if __name__ == "__main__":
    import json

    print(json.dumps(build_scenario_frames(), indent=2, sort_keys=True))
