from copy import deepcopy

from closed_loop_runtime import generate_valid_actions
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_perception import project_environmental_presence
from memoria_v2_adapter import observer_state_addresses
from scenario_life_gate_005 import build_life_gate_005_world
from spatial_runtime import relocate_entity


def _distribution(world):
    return world["entities"]["water_01"]["components"]["environmental_distribution"]


def _by_region(world):
    return dict(_distribution(world)["by_region"])


def _evaporated(world):
    return int(_distribution(world)["evaporated_total"])


def test_first_distributed_tick_splits_retains_and_evaporates_exactly():
    world = build_life_gate_005_world()
    tick = advance_distributed_environmental_agents(world, ticks=1)[0]

    assert _by_region(tick.world) == {
        "channel": 40,
        "hollow": 30,
        "spring": 20,
    }
    assert _evaporated(tick.world) == 10

    spring = next(item for item in tick.balances if item["region_id"] == "spring")
    assert spring["before"] == 100
    assert spring["retained"] == 20
    assert spring["transferred"] == 70
    assert spring["evaporated"] == 10
    assert tuple(
        (item["route_id"], item["amount"])
        for item in spring["transfers"]
    ) == (
        ("spring_channel", 40),
        ("spring_hollow", 30),
    )


def test_new_inflows_are_not_reprocessed_in_same_tick():
    world = build_life_gate_005_world()
    first = advance_distributed_environmental_agents(world, ticks=1)[0]

    # Basin remains empty after tick 1 even though channel/hollow received water.
    assert "basin" not in _by_region(first.world)

    second = advance_distributed_environmental_agents(first.world, ticks=1)[0]
    assert _by_region(second.world) == {
        "basin": 37,
        "channel": 10,
        "hollow": 15,
        "spring": 10,
    }
    assert _evaporated(second.world) == 28


def test_total_quantity_plus_evaporation_is_conserved_across_ticks():
    world = build_life_gate_005_world()
    for tick in advance_distributed_environmental_agents(world, ticks=6):
        distribution = _distribution(tick.world)
        total = sum(distribution["by_region"].values()) + distribution["evaporated_total"]
        assert total == distribution["initial_total"] == 100
        assert all(value >= 0 for value in distribution["by_region"].values())


def test_water_is_present_in_multiple_regions_concurrently():
    world = build_life_gate_005_world()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world

    assert set(_by_region(world)) == {"spring", "channel", "hollow"}

    # Nov remains able to interact at the retained spring quantity.
    spring_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in spring_actions

    world = relocate_entity(world, "nova", "channel")
    channel_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in channel_actions

    world = relocate_entity(world, "nova", "hollow")
    hollow_actions = {item["action"] for item in generate_valid_actions(world, "nova")}
    assert "probe" in hollow_actions


def test_distributed_presence_projection_is_read_only():
    world = build_life_gate_005_world()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world
    before = deepcopy(world)

    projected = project_environmental_presence(world, "nova")
    state = observer_state_addresses(projected, "nova")

    assert "live:entity:water_01" in state
    assert world == before


def test_exact_quantities_do_not_leak_into_cognitive_state_addresses():
    world = build_life_gate_005_world()
    world = advance_distributed_environmental_agents(world, ticks=1)[0].world

    projected = project_environmental_presence(world, "nova")
    state = observer_state_addresses(projected, "nova")

    altered = deepcopy(world)
    altered_distribution = altered["entities"]["water_01"]["components"]["environmental_distribution"]
    altered_distribution["by_region"] = {
        "channel": 59,
        "hollow": 30,
        "spring": 1,
    }
    altered_projected = project_environmental_presence(altered, "nova")
    altered_state = observer_state_addresses(altered_projected, "nova")

    # Same observable presence, different hidden quantities -> identical cognitive state.
    assert altered_state == state
    serialized = "|".join(state)
    for hidden in ("environmental_distribution", "initial_total", "evaporated_total", "by_region"):
        assert hidden not in serialized


def test_distributed_environment_run_is_deterministic():
    def signature():
        world = build_life_gate_005_world()
        ticks = advance_distributed_environmental_agents(world, ticks=4)
        return tuple(
            (
                tuple(sorted(_by_region(tick.world).items())),
                _evaporated(tick.world),
                tuple(
                    (
                        balance["region_id"],
                        balance["before"],
                        balance["retained"],
                        balance["transferred"],
                        balance["evaporated"],
                        tuple(
                            (item["route_id"], item["to_region"], item["amount"])
                            for item in balance["transfers"]
                        ),
                    )
                    for balance in tick.balances
                ),
            )
            for tick in ticks
        )

    assert signature() == signature()
