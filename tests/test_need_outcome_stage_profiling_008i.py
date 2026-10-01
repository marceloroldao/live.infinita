from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"


class NeedOutcomeStageProfiling008ITests(unittest.TestCase):
    def test_profiler_wires_need_and_outcome_components(self) -> None:
        source = (RUNTIME / "tick_driver_main.py").read_text(encoding="utf-8")
        self.assertIn('"npc_need_scheduler"', source)
        self.assertIn('"npc_need_outcomes"', source)
        self.assertIn(
            "component.stage_observer = profiler.observe_stage",
            source,
        )

    def test_rollout_is_observational_and_single_writer_only(self) -> None:
        script = (
            ROOT / "deploy" / "apply-need-outcome-stage-profiling-008i.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("npc_need_scheduler.py", script)
        self.assertIn("npc_need_outcomes.py", script)
        self.assertIn("tick_driver_main.py", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertIn("proposals.jsonl.index.sqlite3", script)
        self.assertIn("world-tick-profile.json", script)
        self.assertNotIn("hot_ledger_compactor", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)

    def test_instrumentation_has_no_direct_world_authority(self) -> None:
        need_source = (RUNTIME / "npc_need_scheduler.py").read_text(encoding="utf-8")
        outcome_source = (RUNTIME / "npc_need_outcomes.py").read_text(encoding="utf-8")
        self.assertIn("need.evaluate.proposal_propose", need_source)
        self.assertIn("need.evaluate.plan_schedule", need_source)
        self.assertIn("outcome.process.satisfy", outcome_source)
        self.assertIn("outcome.process.remember_episode", outcome_source)
        self.assertNotIn("set_world", outcome_source)
        self.assertNotIn("commit_operations(", outcome_source)


if __name__ == "__main__":
    unittest.main()
