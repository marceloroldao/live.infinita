from nov_need_scheduler import (
    advance_needs,
    make_need_state,
    relieve_need,
    select_need_action,
)


def _world():
    return {
        "rules": {
            "actions": [
                {
                    "rule_id": "walk",
                    "action": "walk",
                    "need_affordances": ["roam"],
                },
                {
                    "rule_id": "rest",
                    "action": "rest",
                    "need_affordances": ["recover"],
                },
            ]
        }
    }


def _proposal(rule_id: str, action: str, proposal_id: str):
    return {
        "proposal_id": proposal_id,
        "actor": "nova",
        "action": action,
        "target": None,
        "parameters": {"rule_id": rule_id},
    }


def test_need_pressure_advances_only_by_logical_ticks():
    state = make_need_state(
        tick_id=10,
        pressures={"recover": 1, "roam": 4},
    )

    same = advance_needs(state, tick_id=10)
    later = advance_needs(state, tick_id=15)

    assert same == state
    assert later.tick_id == 15
    assert later.pressure("recover") == 6
    assert later.pressure("roam") == 9


def test_relief_occurs_without_negative_pressure():
    state = make_need_state(
        tick_id=10,
        pressures={"recover": 3, "roam": 7},
    )

    partial = relieve_need(state, "roam", amount=5)
    reset = relieve_need(partial, "recover")

    assert partial.pressure("roam") == 2
    assert partial.pressure("recover") == 3
    assert reset.pressure("recover") == 0


def test_scheduler_selects_highest_pressure_serviceable_need():
    world = _world()
    proposals = (
        _proposal("rest", "rest", "p-rest"),
        _proposal("walk", "walk", "p-walk"),
    )
    needs = make_need_state(
        tick_id=10,
        pressures={"recover": 5, "roam": 9},
    )

    decision = select_need_action(
        world=world,
        proposals=proposals,
        needs=needs,
    )

    assert decision is not None
    assert decision.need_id == "roam"
    assert decision.proposal["proposal_id"] == "p-walk"


def test_scheduler_cannot_invent_action_for_unserviceable_need():
    world = _world()
    proposals = (_proposal("rest", "rest", "p-rest"),)
    needs = make_need_state(
        tick_id=10,
        pressures={"recover": 0, "roam": 9},
    )

    assert select_need_action(
        world=world,
        proposals=proposals,
        needs=needs,
    ) is None


def test_scheduler_tie_is_deterministic_by_need_id_then_proposal():
    world = _world()
    proposals = (
        _proposal("walk", "walk", "p-walk-z"),
        _proposal("rest", "rest", "p-rest"),
        _proposal("walk", "walk", "p-walk-a"),
    )
    needs = make_need_state(
        tick_id=10,
        pressures={"recover": 5, "roam": 5},
    )

    first = select_need_action(world=world, proposals=proposals, needs=needs)
    second = select_need_action(world=world, proposals=tuple(reversed(proposals)), needs=needs)

    assert first == second
    assert first is not None
    assert first.need_id == "recover"
    assert first.proposal["proposal_id"] == "p-rest"
