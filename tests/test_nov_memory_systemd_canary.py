"""Ephemeral systemd canary has strict bounded result and no permanent unit."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))
from nov_memory_release_contract import MODULES, ReleaseBlocked
from nov_memory_systemd_canary import CYCLES, evaluate_journal, render_canary


class SystemdCanaryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "release"
        self.root.mkdir(mode=0o755)
        for module in MODULES:
            p = self.root / (module + ".py")
            p.write_text("# synthetic public module\n")
            p.chmod(0o644)
        self.core = Path(self.tmp.name) / "core"
        (self.core / "memoria_resolutiva").mkdir(parents=True)
        (self.core / "memoria_resolutiva/external_episode_incremental.py").write_text("")
        self.python = Path(self.tmp.name) / "python"
        self.python.write_text("#!/bin/sh\n")
        self.python.chmod(0o755)
        self.template = (ROOT / "deploy/live-infinita-nov-memory-prepare.service").read_text()

    def test_canary_unit_keeps_production_sandbox_but_has_no_install(self):
        unit = render_canary(self.template, self.root,
                             core=self.core, python=self.python)
        self.assertIn("ExecStart=" + str(self.python) + " " + str(self.root)
                      + "/nov_memory_continuous.py --period 2 --refresh 4 --scratch-root /run/live-infinita-nov-preparer --cycles 60", unit)
        self.assertIn("Restart=no", unit)
        self.assertNotIn("Restart=on-failure", unit)
        self.assertNotIn("[Install]", unit)
        self.assertNotIn("WantedBy", unit)
        for entry in (
            "User=liveinfinita", "Group=liveinfinita",
            "ReadOnlyPaths=/var/lib/live-infinita/memoria-local",
            "ReadOnlyPaths=/var/lib/live-infinita/autonomous-world",
            "NoNewPrivileges=true", "PrivateTmp=true",
            "ProtectSystem=strict", "IPAddressDeny=any",
            "MemoryMax=384M", "StartLimitBurst=3",
            "RuntimeDirectory=live-infinita-nov-preparer",
            "RuntimeDirectoryMode=0700",
            "ReadWritePaths=/run/live-infinita-nov-preparer",
        ):
            self.assertIn(entry, unit)

    def test_canary_template_tampering_fails_closed(self):
        for changed in (
            self.template.replace("Restart=on-failure", "Restart=always"),
            self.template.replace(" --period 2 --refresh 4", " --period 1 --refresh 4"),
            self.template.replace("[Install]", ""),
            self.template.replace("ProtectSystem=strict", ""),
        ):
            with self.subTest(changed=changed[:50]), self.assertRaises(ReleaseBlocked):
                render_canary(changed, self.root, core=self.core, python=self.python)

    @staticmethod
    def report():
        return {
            "schema": "live-infinita-nov-owner-continuous/v1",
            "status": "ok", "cycles": CYCLES, "samples": CYCLES,
            "ready_reads": 37, "abstentions": 23, "submissions": 15,
            "longest_not_ready_streak": 6,
            "frame_tick_advances": 51, "frame_tick_regressions": 0,
            "status_counts": {"ready": 37, "pending": 23},
            "peak_rss_kib": 55555, "max_step_ms": 5.3,
            "slow_step_gt_250_count": 0, "slow_step_gt_500_count": 0,
            "historical_snapshot_only": True, "live_caught_up_claim": False,
            "main_runtime_wired": False, "selection_authority": False,
            "world_mutated": False, "central_sync": False, "bdr_used": False,
        }

    def test_valid_redacted_journal_passes(self):
        result = evaluate_journal("MVP018L_OWNER_STATUS {}\n"
            + "MVP018L_OWNER_STOPPED " + json.dumps(self.report()) + "\n")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["ready_reads"], 37)
        self.assertNotIn("record_key", json.dumps(result))
        self.assertNotIn("live:world", json.dumps(result))

    def test_gate_refuses_missing_double_or_untrusted_marker(self):
        report = json.dumps(self.report())
        self.assertEqual(evaluate_journal("")["reasons"], ["aggregate_marker"])
        self.assertEqual(evaluate_journal("MVP018L_OWNER_STOPPED " + report
            + "\nMVP018L_OWNER_STOPPED " + report)["reasons"], ["aggregate_marker"])
        self.assertEqual(evaluate_journal("MVP018L_OWNER_STOPPED not-json")["reasons"],
                         ["aggregate_json"])
        self.assertEqual(evaluate_journal("x" * 65537)["reasons"], ["journal_budget"])

    def test_bad_accounting_or_authority_never_passes(self):
        for update, code in (
            ({"ready_reads": 0, "abstentions": CYCLES, "status_counts": {"pending": CYCLES}},
             "readiness_or_accounting"),
            ({"cycles": 11}, "readiness_or_accounting"),
            ({"ready_reads": 11, "abstentions": 49,
              "status_counts": {"ready": 11, "pending": 49}}, "readiness_or_accounting"),
            ({"longest_not_ready_streak": 21}, "readiness_or_accounting"),
            ({"frame_tick_regressions": 1}, "readiness_or_accounting"),
            ({"selection_authority": True}, "authority_contract"),
            ({"main_runtime_wired": True}, "authority_contract"),
            ({"world_mutated": True}, "authority_contract"),
            ({"max_step_ms": 760.384, "slow_step_gt_250_count": 1,
              "slow_step_gt_500_count": 1}, "resource_budget"),
            ({"peak_rss_kib": 400000}, "resource_budget"),
            ({"status_counts": {"ready": 37, "private": 23}}, "readiness_or_accounting"),
        ):
            with self.subTest(update=update):
                r = self.report()
                r.update(update)
                self.assertEqual(
                    evaluate_journal("MVP018L_OWNER_STOPPED " + json.dumps(r))["reasons"],
                    [code],
                )

    def test_operator_and_root_script_leave_no_unit_or_release(self):
        operator = (ROOT / "deploy/mvp018o-nov-systemd-canary.sh").read_text()
        root_script = (ROOT / "deploy/mvp018o-nov-systemd-canary-root.sh").read_text()
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertIn("sudo -v", operator)
        self.assertIn("sudo -n -- bash", operator)
        self.assertIn("git -c safe.directory", root_script)
        self.assertIn('show \\', root_script)
        self.assertIn('trap cleanup EXIT', root_script)
        self.assertIn('systemctl stop "$UNIT"', root_script)
        self.assertIn('systemctl reset-failed "$UNIT"', root_script)
        self.assertIn('"$RELEASE"', root_script)
        self.assertIn("MVP018O_NO_PERMANENT_UNIT_OR_CUTOVER", root_script)
        self.assertNotIn("systemctl enable ", root_script)
        self.assertNotIn("systemctl restart ", root_script)
        self.assertNotIn("memory_recall_provider=", runtime)
        self.assertNotIn("prepared_memory_provider=", runtime)


if __name__ == "__main__":
    unittest.main()
