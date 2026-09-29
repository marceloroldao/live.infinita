"""MVP-018M operational canary: strict redacted, independent of action quality."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_operational_gate import (
    EXPECTED_CYCLES, MAX_LOG_BYTES, evaluate_operational, load_redacted_report,
)


def sample() -> dict:
    return {
        "schema": "live-infinita-nov-owner-continuous/v1",
        "status": "ok", "cycles": EXPECTED_CYCLES, "samples": 64,
        "ready_reads": 37, "abstentions": 27, "submissions": 14,
        "status_counts": {
            "ready": 37, "pending": 13, "frame_unavailable": 8,
            "query_changed": 4, "source_changed": 2,
        },
        "ready_fraction": round(37 / 64, 4),
        "longest_not_ready_streak": 6,
        "frame_tick_advances": 51, "frame_tick_regressions": 0,
        "peak_rss_kib": 53248, "max_step_ms": 37.2,
        "median_step_ms": 1.98,
        "historical_snapshot_only": True, "live_caught_up_claim": False,
        "main_runtime_wired": False, "selection_authority": False,
        "world_mutated": False, "central_sync": False, "bdr_used": False,
    }


class OperationalGateTests(unittest.TestCase):
    def test_healthy_finite_owner_canary_passes_without_claims(self):
        result = evaluate_operational(sample())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["reasons"], [])
        self.assertFalse(result["main_runtime_wired"])
        self.assertFalse(result["selection_authority"])
        self.assertNotIn("record_key", json.dumps(result))
        self.assertNotIn("region", json.dumps(result))
        self.assertNotIn("evidence_id", json.dumps(result))

    def test_low_readiness_and_long_streak_fail_closed(self):
        report = sample()
        report["ready_reads"], report["abstentions"] = 8, 56
        report["status_counts"] = {"ready": 8, "pending": 56}
        report["ready_fraction"] = 0.125
        report["longest_not_ready_streak"] = 34
        result = evaluate_operational(report)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("readiness_budget", result["reasons"])

    def test_accounting_statuses_and_identity_fail_closed(self):
        for change, reason in (
            ({"samples": 3}, "accounting_invalid"),
            ({"cycles": 6}, "accounting_invalid"),
            ({"status_counts": {"ready": 37, "private_address": 27}},
             "status_accounting_invalid"),
            ({"ready_fraction": 0.99}, "readiness_fraction_invalid"),
            ({"selection_authority": True}, "authority_contract"),
            ({"live_caught_up_claim": True}, "authority_contract"),
            ({"world_mutated": True}, "authority_contract"),
            ({"main_runtime_wired": True}, "authority_contract"),
            ({"frame_tick_regressions": 1}, "frame_progress_budget"),
            ({"frame_tick_advances": 0}, "frame_progress_budget"),
            ({"peak_rss_kib": 400000}, "resource_budget"),
            ({"max_step_ms": 270.0}, "resource_budget"),
        ):
            with self.subTest(change=change):
                value = sample()
                value.update(change)
                report = evaluate_operational(value)
                self.assertEqual(report["status"], "blocked")
                self.assertIn(reason, report["reasons"])
        self.assertEqual(evaluate_operational({"schema": "wrong"})["reasons"],
                         ["schema_invalid"])
        self.assertIn("metrics_invalid",
                      evaluate_operational({**sample(), "samples": True})["reasons"])

    def test_source_changes_are_measurements_not_forced_failures(self):
        report = sample()
        report["status_counts"] = {
            "ready": 37, "source_changed": 15,
            "frame_unavailable": 12,
        }
        self.assertEqual(evaluate_operational(report)["status"], "pass")

    def test_log_validation_permissions_symlink_single_marker(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "canary.log"
            path.write_text("MVP018L_OWNER_STATUS {}\nMVP018L_OWNER_CANARY_OK "
                            + json.dumps(sample()) + "\n")
            path.chmod(0o600)
            self.assertEqual(load_redacted_report(path)["ready_reads"], 37)
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                load_redacted_report(path)
            path.chmod(0o600)
            link = Path(root) / "link.log"
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                load_redacted_report(link)
            path.write_text("MVP018L_OWNER_CANARY_OK " + json.dumps(sample())
                            + "\nMVP018L_OWNER_CANARY_OK " + json.dumps(sample()))
            with self.assertRaises(ValueError):
                load_redacted_report(path)
            path.write_text("a" * (MAX_LOG_BYTES + 1))
            with self.assertRaises(ValueError):
                load_redacted_report(path)

    def test_deploy_script_stages_only_public_code_and_no_live_wiring(self):
        script = (ROOT / "deploy/mvp018m-nov-extended-canary.sh").read_text()
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertIn("--cycles 60 --period 2 --refresh 4", script)
        self.assertIn("sudo -v", script)
        self.assertIn("sudo -n -u liveinfinita", script)
        self.assertIn("nov-memory-extended-canary.log", script)
        self.assertIn("nov_memory_operational_gate", script)
        self.assertIn("systemctl is-active", script)
        self.assertNotIn("systemctl restart", script)
        self.assertNotIn("systemctl enable", script)
        self.assertNotIn("cp -- \"$ROOT", script)
        self.assertNotIn("memory_recall_provider=", runtime)
        self.assertNotIn("prepared_memory_provider=", runtime)


if __name__ == "__main__":
    unittest.main()
