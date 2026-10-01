from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"


class ReduceSyncBarriers008KTests(unittest.TestCase):
    def test_idle_ephemeral_is_same_region_only(self) -> None:
        source = (RUNTIME / "npc_idle_wander.py").read_text(encoding="utf-8")
        self.assertIn(
            'if region.id == current_id and callable(execute_ephemeral):',
            source,
        )
        self.assertIn("execute_ephemeral_one_step", source)
        self.assertIn("self.plans.schedule(", source)
        self.assertIn('"ephemeral": True', source)
        self.assertIn('"ephemeral": False', source)

    def test_ephemeral_scheduler_keeps_guarded_mutation_path(self) -> None:
        source = (RUNTIME / "plan_scheduler.py").read_text(encoding="utf-8")
        self.assertIn("def execute_ephemeral_one_step(", source)
        self.assertIn("ephemeral execution requires exactly one step", source)
        self.assertIn("self.guarded.commit(", source)
        block = source.split("def execute_ephemeral_one_step(", 1)[1].split(
            "def assess_resume(", 1
        )[0]
        self.assertNotIn("self.ledger.create(", block)
        self.assertNotIn("self.ledger.transition(", block)

    def test_need_scheduler_uses_atomic_propose_approved_when_available(self) -> None:
        source = (
            RUNTIME / "npc_reordering_need_scheduler.py"
        ).read_text(encoding="utf-8")
        self.assertIn('getattr(self.proposals, "propose_approved", None)', source)
        self.assertIn("need.evaluate.proposal_propose_approved", source)
        self.assertIn("self.proposals.propose(", source)
        self.assertIn("self.proposals.approve(", source)

    def test_proposal_pair_keeps_fsync_and_two_records(self) -> None:
        source = (RUNTIME / "proposal_ledger.py").read_text(encoding="utf-8")
        self.assertIn("def _append_transition_pair(", source)
        self.assertIn("def propose_approved(", source)
        self.assertIn("os.fsync(fd)", source)
        self.assertIn('"status": "proposed"', source)
        self.assertIn('second["status"] = "approved"', source)

    def test_rollout_only_restarts_single_writer(self) -> None:
        script = (
            ROOT / "deploy" / "apply-reduce-sync-barriers-008k.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('systemctl stop "$SERVICE"', script)
        self.assertIn("current_tick >= baseline_tick + 2", script)
        self.assertIn("plans.jsonl.index.sqlite3", script)
        self.assertIn("proposals.jsonl.index.sqlite3", script)
        self.assertIn("LIVE_INFINITA_WORLD_BUILDER=1", script)
        self.assertNotIn("systemctl restart live-infinita.service", script)
        self.assertNotIn("systemctl restart live-infinita-renderer.service", script)
        self.assertNotIn("systemctl restart live-infinita-memoria-local.service", script)


if __name__ == "__main__":
    unittest.main()
