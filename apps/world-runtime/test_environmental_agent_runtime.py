from copy import deepcopy

from closed_loop_runtime import generate_valid_actions
from environmental_agent_runtime import advance_environmental_agents
from environmental_perception import project_environmental_presence
from memoria_v2_adapter import observer_state_addresses
from scenario_life_gate_003 import build_life_gate_003_world
from spatial_runtime import relocate_entity


def _water_region(world):
    return world["entities"]["water_01"]["components"]["transform"]["region_id"]


def _presence_relations(world):
    projected = project_environmental_presence(world, "nova")
    return [
        relation
        for relation in projected["relations"].values()
        if relation.get("source", {}).get("type") == "environmental-presence-projection"
    ]


def test_environmental_agent_advances_on_logical_ticks_and_leaves_trace():
    world = build_life_gate_003_world()

    first_three = advance_environmental_agents(world, ticks=3)
    assert all(not tick.transitions for tick in first_three)
    world = first_three[-1].world
    assert _water_region(world) == "spring"

    fourth = advance_environmental_agents(world, ticks=1)[0]
    assert len(fourth.transitions) == 1
    assert fourth.transitions[0]["from_region"] == "spring"
    assert fourth.transitions[0]["to_region"] == "stream"
    assert _water_region(fourth.world) == "stream"

    trace_id = fourth.transitions[0]["trace_id"]
    trace = fourth.world["entities"][trace_id]
    assert trace["class"] == "environment_trace"
    assert trace["components"]["transform"]["region_id"] == "spring"
    assert trace["components"]["origin"]["agent_id"] == "water_01"


def test_environmental_presence_projection_is_read_only_and_spatial():
    world = build_life_gate_003_world()
    before = deepcopy(world)

    present = _presence_relations(world)
    assert len(present) == 1
    assert present[0]["subject"] == "nova"
    assert present[0]["object"] == "water_01"
    assert world == before

    world = advance_environmental_agents(world, ticks=4)[-1].world
    assert _water_region(world) == "stream"
    assert _presence_relations(world) == []


def test_colocation_guard_removes_and_restores_water_action():
    world = build_life_gate_003_world()

    initial_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in initial_actions

    world = advance_environmental_agents(world, ticks=4)[-1].world
    separated_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" not in separated_actions

    world = relocate_entity(world, "nova", "stream")
    reunited_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in reunited_actions


def test_environmental_projection_changes_cognitive_state_without_world_mutation():
    world = build_life_gate_003_world()

    projected = project_environmental_presence(world, "nova")
    state_with_water = observer_state_addresses(projected, "nova")
    assert "live:entity:water_01" in state_with_water

    moved = advance_environmental_agents(world, ticks=4)[-1].world
    projected_after = project_environmental_presence(moved, "nova")
    state_without_water = observer_state_addresses(projected_after, "nova")

    assert "live:entity:water_01" not in state_without_water
    assert state_with_water != state_without_water


def test_environmental_agent_run_is_deterministic():
    def signature():
        world = build_life_gate_003_world()
        ticks = advance_environmental_agents(world, ticks=7)
        final = ticks[-1].world
        traces = tuple(
            sorted(
                (
                    entity_id,
                    entity["components"]["transform"]["region_id"],
                    entity["components"]["address"]["value"],
                )
                for entity_id, entity in final["entities"].items()
                if entity.get("class") == "environment_trace"
            )
        )
        transitions = tuple(
            tuple(
                (
                    item["agent_id"],
                    item["from_region"],
                    item["to_region"],
                    item["generation"],
                )
                for item in tick.transitions
            )
            for tick in ticks
        )
        return (
            final["current_tick"],
            final["current_version"],
            _water_region(final),
            traces,
            transitions,
        )

    assert signature() == signature()
