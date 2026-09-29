"""Static and isolated owner-only MVP-018E audit regression tests."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "deploy/mvp018e_bdr_shadow_audit.py"
spec = importlib.util.spec_from_file_location("mirror_audit", MODULE)
audit_module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(audit_module)


def proof() -> dict:
    return {
        "schema": audit_module.SCHEMA,
        "source_snapshot_records": 5, "inserted_into_bdr": 5,
        "bdr_durable_sequence": 8,
        "record_manifest_sha256": "a" * 64,
        "evidence_graph_sha256": "b" * 64,
        "sqlite_snapshot_bytes": 4096, "bdr_candidate_bytes": 4096,
        "source_mode": "sqlite-online-backup-read-only",
        "checkpoint_watermark_present": True,
        "checkpoint_unchanged_during_copy": True,
        "sqlite_source_inode_unchanged": True,
        "verified_cold_restart": True, "verified_idempotent_replay": True,
        "backend_cutover": False, "production_checkpoint_advanced": False,
        "world_mutated": False, "central_sync": False,
    }


class AuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "bdr-mirrors"
        self.root.mkdir(mode=0o700)
        self.run = self.root / "20260929T161000Z-999"
        self.run.mkdir(mode=0o700)
        self.report = self.run / "report.json"
        self.write(proof())

    def write(self, data: dict) -> None:
        self.report.write_text(json.dumps(data))
        self.report.chmod(0o600)

    def test_good_proof_is_historical_not_live_cutover(self) -> None:
        result = audit_module.audit(self.root)
        self.assertEqual(result["snapshot_records"], 5)
        self.assertTrue(result["snapshot_parity"])
        self.assertFalse(result["backend_cutover"])
        self.assertFalse(result["live_caught_up_claim"])

    def test_moving_checkpoint_is_reported_but_snapshot_valid(self) -> None:
        data = proof()
        data["checkpoint_unchanged_during_copy"] = False
        self.write(data)
        result = audit_module.audit(self.root)
        self.assertIs(result["checkpoint_unchanged_during_copy"], False)
        self.assertIs(result["live_caught_up_claim"], False)

    def test_missing_latest_report_does_not_fall_back(self) -> None:
        newer = self.root / "20260929T162000Z-999"
        newer.mkdir(mode=0o700)
        with self.assertRaises(OSError):
            audit_module.audit(self.root)

    def test_partial_and_false_proofs_fail_closed(self) -> None:
        for name, value in (
            ("schema", "wrong"), ("inserted_into_bdr", 4),
            ("bdr_durable_sequence", 0), ("record_manifest_sha256", "bad"),
            ("checkpoint_watermark_present", False),
            ("verified_idempotent_replay", False),
            ("backend_cutover", True), ("production_checkpoint_advanced", True),
            ("world_mutated", True), ("central_sync", True),
            ("sqlite_source_inode_unchanged", False),
            ("checkpoint_unchanged_during_copy", None),
        ):
            with self.subTest(name=name):
                data = proof()
                data[name] = value
                self.write(data)
                with self.assertRaises(audit_module.AuditError):
                    audit_module.audit(self.root)

    def test_unsafe_mode_and_symlink_rejected(self) -> None:
        self.report.chmod(0o644)
        with self.assertRaises(audit_module.AuditError):
            audit_module.audit(self.root)
        self.report.unlink()
        outside = Path(self.temp.name) / "outside.json"
        outside.write_text(json.dumps(proof()))
        self.report.symlink_to(outside)
        with self.assertRaises(audit_module.AuditError):
            audit_module.audit(self.root)

    def test_wrapper_uses_stdin_not_private_home_script_path(self) -> None:
        wrapper = (MODULE.parent / "mvp018e-bdr-shadow-audit.sh").read_text()
        self.assertIn(
            'sudo -u liveinfinita "$PY" - --mirrors-root "$ROOT" < '
            '"$REPO/deploy/mvp018e_bdr_shadow_audit.py"', wrapper,
        )
        self.assertIn('( cd / && sudo -u liveinfinita', wrapper)
        self.assertNotIn(
            'sudo -u liveinfinita "$PY" "$REPO/deploy/mvp018e_bdr_shadow_audit.py"',
            wrapper,
        )
        for unsafe in ("chmod 755 /home/etbra", "setfacl", "chown -R", "cp -r"):
            self.assertNotIn(unsafe, wrapper)

    def test_no_payload_or_hash_leaks_from_summary(self) -> None:
        output = json.dumps(audit_module.audit(self.root))
        self.assertNotIn("a" * 64, output)
        self.assertNotIn("b" * 64, output)
        self.assertNotIn("record_key", output)


if __name__ == "__main__":
    unittest.main()
