from copy import deepcopy

from memoria_v2_adapter import (
    build_cognitive_frame,
    candidate_from_transition,
    observer_state_addresses,
    to_memoria_v2_request_payload,
)


def _world(region="r1", tick=1, version=1):
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
            "rel_near": {
                "relation_id": "rel_near",
                "subject": "nova",
                "predicate": "near",
                "object": "fire",
                "status": "active",
            }
        },
    }


def _proposal(pid="p1", action="approach", target="fire"):
    return {
        "proposal_id": pid,
        "actor": "nova",
        "action": action,
        "target": target,
        "source": "memoria-v2-gym",
        "tick_id": 1,
    }


def test_projection_is_deterministic():
    world = _world()
    assert observer_state_addresses(world, "nova") == observer_state_addresses(world, "nova")


def test_semantic_predicate_does_not_become_core_address():
    addresses = observer_state_addresses(_world(), "nova")
    assert not any("near" in item for item in addresses)
    assert "live:relation:rel_near" in addresses


def test_frame_is_deterministic_under_proposal_order():
    world = _world()
    a = build_cognitive_frame(
        world=world,
        observer_id="nova",
        proposals=(_proposal("p2", "wait", None), _proposal("p1")),
    )
    b = build_cognitive_frame(
        world=world,
        observer_id="nova",
        proposals=(_proposal("p1"), _proposal("p2", "wait", None)),
    )
    assert a == b


def test_region_change_becomes_observable_consequence():
    before = _world(region="r1", tick=1)
    after = _world(region="r2", tick=2, version=2)
    candidate = candidate_from_transition(
        candidate_id="c1",
        proposal_id="p1",
        before=before,
        after=after,
        observer_id="nova",
        event_ids=("e1",),
    )
    assert candidate.proposal_id == "p1"
    assert "live:region:r2" in candidate.consequence_addresses
    assert "live:region:r1" not in candidate.next_state_addresses


def test_no_structural_change_is_explicit_not_fabricated():
    before = _world()
    after = deepcopy(before)
    after["current_tick"] = 2
    candidate = candidate_from_transition(
        candidate_id="c0",
        proposal_id="p1",
        before=before,
        after=after,
        observer_id="nova",
    )
    assert candidate.consequence_addresses == ("live:outcome:no-structural-change",)


def test_candidate_for_unknown_proposal_fails_closed():
    candidate = candidate_from_transition(
        candidate_id="c1",
        proposal_id="missing",
        before=_world(region="r1"),
        after=_world(region="r2", tick=2, version=2),
        observer_id="nova",
    )
    try:
        build_cognitive_frame(
            world=_world(),
            observer_id="nova",
            proposals=(_proposal("p1"),),
            candidates=(candidate,),
        )
    except ValueError as exc:
        assert "available proposal_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_selected_request_contains_only_candidates_for_selected_intervention():
    before = _world(region="r1")
    c1 = candidate_from_transition(
        candidate_id="c1",
        proposal_id="p1",
        before=before,
        after=_world(region="r2", tick=2, version=2),
        observer_id="nova",
    )
    c2 = candidate_from_transition(
        candidate_id="c2",
        proposal_id="p2",
        before=before,
        after=deepcopy(before),
        observer_id="nova",
    )
    frame = build_cognitive_frame(
        world=before,
        observer_id="nova",
        proposals=(_proposal("p1"), _proposal("p2", "wait", None)),
        candidates=(c1, c2),
    )
    payload = to_memoria_v2_request_payload(frame, proposal_id="p1")
    assert payload["intervention_id"] == "p1"
    assert tuple(item[0] for item in payload["candidates"]) == ("c1",)


def test_unknown_observer_fails_closed():
    try:
        observer_state_addresses(_world(), "ghost")
    except ValueError as exc:
        assert "unknown observer_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_duplicate_proposal_ids_fail_closed():
    try:
        build_cognitive_frame(
            world=_world(),
            observer_id="nova",
            proposals=(_proposal("same"), _proposal("same", "wait", None)),
        )
    except ValueError as exc:
        assert "proposal_id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
