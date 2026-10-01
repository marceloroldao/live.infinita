from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"


class DurableAppendStageProfiling008JTests(unittest.TestCase):
    def test_tick_profiler_wires_plan_ledger(self) -> None:
        source = (RUNTIME / "tick_driver_main.py").read_text(encoding="utf-8")
        self.assertIn(
            "ledger.stage_observer = profiler.observe_stage",
            source,
        )

    def test_production_reordering_scheduler_is_instrumented(self) -> None:
        source = (
            RUNTIME / "npc_reordering_need_scheduler.py"
        ).read_text(encoding="utf-8")
        for name in (
            "need.evaluate.entity",
            "need.evaluate.need_values",
            "need.evaluate.context",
            "need.evaluate.prepare_need",
            "need.evaluate.proposal_propose",
            "need.evaluate.proposal_approve",
            "need.evaluate.plan_schedule",
            "need.evaluate.audit_append",
        ):
            self.assertIn(name, source)

    def test_plan_ledger_measures_durable_append_without_removing_fsync(self) -> None:
        source = (RUNTIME / "plan_ledger.py").read_text(encoding="utf-8")
        self.assertIn("plan.ledger.append.write", source)
        self.assertIn("plan.ledger.append.fsync", source)
        self.assertIn("plan.ledger.append.sidecar", source)
        self.assertIn("os.fsync(fd)", source)

    def test_rollout_is_observational_and_single_writer_only(self) -> None:
        script = (
            ROOT / "deploy" / "apply-durable-append-stage-profiling-008j.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("npc_reordering_need_scheduler.py", script)
        self.assertIn("plan_ledger.py", script)
        self.assertIn("tick_driver_main.py", script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertIn("proposals.jsonl.index.sqlite3", script)
        self.assertNotIn("hot_ledger_compactor", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)


if __name__ == "__main__":
    unittest.main()
