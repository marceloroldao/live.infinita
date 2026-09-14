import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from tick_driver_main import build_autonomous_world_tick


class FakeClock:
    pass


class FakeStore:
    def get_entity(self, entity_id):
        if entity_id == "npc":
            return {
                "id": "npc",
                "type": "human",
                "region_id": "r0",
                "properties": {"needs": {}},
            }
        return None


class FakeRegions:
    def route(self, start, end):
        return [start] if start == end else [start, end]


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()
        self.regions = FakeRegions()


class FakeLedger:
    def current(self):
        return []

    def get(self, plan_id):
        return None


class FakeScheduler:
    def __init__(self):
        self.planner = FakePlanner()
        self.ledger = FakeLedger()


class FakeProposalLedger:
    pass


class FakeArbiter:
    def reconcile(self):
        return {
            "runnable": [],
            "preemptions": [],
            "resumptions": [],
            "replans": [],
            "cancellations": [],
        }


class TickDriverCognitiveCompositionTest(unittest.TestCase):
    def test_builder_composes_runner_without_starting_driver(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            clock = FakeClock()
            scheduler = FakeScheduler()
            runner, cognition = build_autonomous_world_tick(
                clock=clock,
                scheduler=scheduler,
                proposal_ledger=FakeProposalLedger(),
                data_dir=Path(tmpdir),
                npc_ids=["npc"],
                plan_arbiter=FakeArbiter(),
            )

            self.assertIs(runner.clock, clock)
            self.assertIs(runner.scheduler, scheduler)
            self.assertIs(runner.npc_need_scheduler, cognition.need_scheduler)
            self.assertIs(runner.npc_need_dynamics, cognition.need_dynamics)
            self.assertIs(runner.npc_need_outcomes, cognition.need_outcomes)
            self.assertIs(runner.npc_strategy_executor, cognition.strategy_executor)
            self.assertIs(
                runner.npc_composite_strategy_outcomes,
                cognition.composite_strategy_outcomes,
            )
            self.assertFalse((Path(tmpdir) / "world-tick.lock").exists())


if __name__ == "__main__":
    unittest.main()
