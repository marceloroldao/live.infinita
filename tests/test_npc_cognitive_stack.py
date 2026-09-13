import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_cognitive_stack import build_npc_cognitive_stack


class FakeStore:
    def __init__(self):
        self.rows = {
            "npc": {
                "id": "npc",
                "type": "human",
                "region_id": "r0",
                "position": {"x": 0, "y": 0},
                "properties": {"needs": {"energy": 0.8}, "rest_target_entity_id": "bed"},
            },
            "bed": {
                "id": "bed",
                "type": "place",
                "region_id": "r0",
                "position": {"x": 10, "y": 0},
                "properties": {},
            },
        }

    def get_entity(self, entity_id):
        return self.rows.get(entity_id)


class FakeRegions:
    def route(self, start, end):
        return [start] if start == end else [start, end]


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()
        self.regions = FakeRegions()


class FakeLedger:
    def __init__(self):
        self.rows = {}

    def get(self, plan_id):
        return self.rows.get(plan_id)

    def current(self):
        return list(self.rows.values())


class FakePlanScheduler:
    def __init__(self):
        self.planner = FakePlanner()
        self.ledger = FakeLedger()


class FakeProposalLedger:
    pass


class NpcCognitiveStackTest(unittest.TestCase):
    def test_builder_wires_shared_learning_and_world_tick_dependencies(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            scheduler = FakePlanScheduler()
            stack = build_npc_cognitive_stack(
                data_dir=Path(tmpdir),
                proposal_ledger=FakeProposalLedger(),
                plan_scheduler=scheduler,
                npc_ids=["npc"],
                strategy_min_samples=1,
            )

            self.assertIs(stack.need_scheduler.need_state_provider, stack.need_dynamics)
            self.assertIs(stack.need_scheduler.learning_provider, stack.need_learning)
            self.assertIs(stack.need_scheduler.strategy_provider, stack.strategy_value)
            self.assertIs(stack.need_scheduler.composite_strategy_provider, stack.composite_strategy)
            self.assertIs(stack.need_scheduler.strategy_compiler, stack.strategy_compiler)
            self.assertIs(stack.need_scheduler.strategy_executor, stack.strategy_executor)
            self.assertIs(stack.composite_strategy.strategy_experience_provider, stack.strategy_experience)
            self.assertIs(stack.strategy_value.strategy_experience_provider, stack.strategy_experience)
            self.assertIs(stack.need_outcomes.strategy_experience_provider, stack.strategy_experience)
            self.assertIs(stack.need_outcomes.episodic_memory_provider, stack.episodic_memory)
            self.assertIs(stack.composite_strategy_outcomes.strategy_experience_provider, stack.strategy_experience)
            self.assertIsNone(stack.composite_strategy_outcomes.episodic_memory_provider)

            kwargs = stack.world_tick_kwargs()
            self.assertIs(kwargs["npc_need_scheduler"], stack.need_scheduler)
            self.assertIs(kwargs["npc_need_dynamics"], stack.need_dynamics)
            self.assertIs(kwargs["npc_need_outcomes"], stack.need_outcomes)
            self.assertIs(kwargs["npc_strategy_executor"], stack.strategy_executor)
            self.assertIs(kwargs["npc_composite_strategy_outcomes"], stack.composite_strategy_outcomes)

    def test_strategy_experience_and_episodes_persist_across_stack_rebuild(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            scheduler = FakePlanScheduler()
            first = build_npc_cognitive_stack(
                data_dir=root,
                proposal_ledger=FakeProposalLedger(),
                plan_scheduler=scheduler,
                npc_ids=["npc"],
                strategy_min_samples=1,
            )
            ctx = {"period": "night", "weather": "storm", "region_id": "r0", "danger_level": 0.8}
            first.strategy_experience.observe_strategy(
                outcome_id="o1",
                npc_id="npc",
                need="energy",
                target_entity_id="bed",
                strategy_id="direct",
                context=ctx,
                satisfaction=0.4,
                elapsed_ticks=3,
                preemptions=0,
                replans=0,
                observed_risk=0.2,
            )
            first.episodic_memory.remember(
                episode_id="episode-1",
                npc_id="npc",
                logical_tick=7,
                need="energy",
                target_entity_id="bed",
                strategy_id="direct",
                context=ctx,
                satisfaction=0.4,
                elapsed_ticks=3,
                observed_risk=0.2,
            )

            second = build_npc_cognitive_stack(
                data_dir=root,
                proposal_ledger=FakeProposalLedger(),
                plan_scheduler=scheduler,
                npc_ids=["npc"],
                strategy_min_samples=1,
            )
            stats = second.strategy_experience.strategy_stats("npc", "energy", "bed", "direct", ctx)
            self.assertIsNotNone(stats)
            self.assertEqual(stats["count"], 1)
            self.assertAlmostEqual(stats["mean_satisfaction"], 0.4)
            recalled = second.episodic_memory.recall("npc", need="energy", context=ctx)
            self.assertEqual([row["episode_id"] for row in recalled], ["episode-1"])

    def test_builder_fails_closed_without_required_scheduler_contract(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            class Broken:
                pass

            with self.assertRaises(ValueError):
                build_npc_cognitive_stack(
                    data_dir=Path(tmpdir),
                    proposal_ledger=FakeProposalLedger(),
                    plan_scheduler=Broken(),
                    npc_ids=["npc"],
                )

    def test_builder_rejects_empty_npc_set(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_npc_cognitive_stack(
                    data_dir=Path(tmpdir),
                    proposal_ledger=FakeProposalLedger(),
                    plan_scheduler=FakePlanScheduler(),
                    npc_ids=[],
                )


if __name__ == "__main__":
    unittest.main()
