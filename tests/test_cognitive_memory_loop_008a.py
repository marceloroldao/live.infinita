from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from packages.observability.cognitive_evidence import (
    CognitiveEvidenceError,
    CognitiveEvidenceLedger,
    audience_comment_evidence,
    narrator_output_evidence,
    to_structural_text_request,
)
import cognitive_evidence_sync as sync


def world(sequence: int = 7) -> dict:
    return {
        "world_id": "nov-live-autonomous-001",
        "sequence": sequence,
        "current_tick": 1234,
        "environment": {
            "region_id": "cave",
            "biome": "rocky",
            "period": "night",
            "weather": "clear",
        },
    }


def comment(text: str = "Nov entra na caverna") -> dict:
    return {
        "source": "tiktok",
        "source_event_id": "msg-123",
        "actor_id": "viewer-7",
        "display_name": "Marcelo",
        "text": text,
    }


def cue(text: str = "Vocês querem mesmo mandar o Nov para a caverna?") -> dict:
    return {
        "cue_id": "interaction-msg-123",
        "text": text,
        "mode": "individual",
        "participants": 3,
        "source": "tiktok",
        "actor_id": "viewer-7",
        "display_name": "Marcelo",
        "generated_by": "fallback:test",
    }


def receipt(*, duplicate: bool = False) -> dict:
    return {
        "stored": not duplicate,
        "duplicate": duplicate,
        "observation_id": "structural-event:" + "a" * 40,
        "association_sync_observations": 1,
        "symbol_count": 4,
        "semantic_projection": False,
    }


class CognitiveEvidenceContractTests(unittest.TestCase):
    def test_audience_and_narrator_are_separate_epistemic_lanes(self) -> None:
        observed = audience_comment_evidence(world(), comment())
        generated = narrator_output_evidence(
            world(),
            cue(),
            causal_parent_record_keys=[observed["record_key"]],
        )

        self.assertEqual(
            observed["provenance"]["epistemic_class"],
            "external_expression",
        )
        self.assertTrue(observed["memory_policy"]["can_reinforce_observed"])
        self.assertIn(
            ":audience-observed",
            observed["memory_policy"]["hierarchy_id"],
        )

        self.assertEqual(
            generated["provenance"]["epistemic_class"],
            "generated_interpretation",
        )
        self.assertFalse(generated["memory_policy"]["can_reinforce_observed"])
        self.assertIn(
            ":narrator-generated",
            generated["memory_policy"]["hierarchy_id"],
        )
        self.assertNotEqual(
            observed["memory_policy"]["hierarchy_id"],
            generated["memory_policy"]["hierarchy_id"],
        )
        self.assertEqual(
            generated["provenance"]["causal_parent_record_keys"],
            [observed["record_key"]],
        )

    def test_structural_requests_preserve_speaker_but_not_same_hierarchy(self) -> None:
        observed = audience_comment_evidence(world(), comment())
        generated = narrator_output_evidence(
            world(),
            cue(),
            causal_parent_record_keys=[observed["record_key"]],
        )
        audience_request = to_structural_text_request(observed)
        narrator_request = to_structural_text_request(generated)

        self.assertEqual(audience_request["source_kind"], "audience_comment")
        self.assertTrue(audience_request["text"].startswith("[viewer:Marcelo]"))
        self.assertEqual(narrator_request["source_kind"], "narrator_output")
        self.assertTrue(narrator_request["text"].startswith("[narrator]"))
        self.assertNotEqual(
            audience_request["hierarchy_id"],
            narrator_request["hierarchy_id"],
        )

    def test_evidence_identity_is_stable_and_conflicts_fail_closed(self) -> None:
        first = audience_comment_evidence(world(), comment())
        same = audience_comment_evidence(world(), deepcopy(comment()))
        self.assertEqual(first, same)

        changed = audience_comment_evidence(world(), comment("texto alterado"))
        self.assertEqual(changed["record_key"], first["record_key"])
        self.assertNotEqual(changed["content_sha256"], first["content_sha256"])

        with tempfile.TemporaryDirectory() as directory:
            ledger = CognitiveEvidenceLedger(Path(directory) / "evidence.jsonl")
            self.assertTrue(ledger.append(first)["stored"])
            self.assertFalse(ledger.append(same)["stored"])
            with self.assertRaisesRegex(
                CognitiveEvidenceError,
                "conflicting cognitive evidence identity",
            ):
                ledger.append(changed)
            restarted = CognitiveEvidenceLedger(ledger.path)
            self.assertEqual(restarted.count, 1)


class CognitiveEvidenceSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="cognitive-evidence-008a-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ledger_path = self.root / "cognitive-evidence.jsonl"
        self.checkpoint = self.root / "checkpoint.json"
        ledger = CognitiveEvidenceLedger(self.ledger_path)
        self.audience = audience_comment_evidence(world(), comment())
        ledger.append(self.audience)
        self.narrator = narrator_output_evidence(
            world(8),
            cue(),
            causal_parent_record_keys=[self.audience["record_key"]],
        )
        ledger.append(self.narrator)

    def test_sync_acks_only_after_valid_receipt_and_resumes(self) -> None:
        sent: list[dict] = []

        def send(payload):
            sent.append(payload)
            return receipt()

        first = sync.sync_once(
            self.ledger_path,
            self.checkpoint,
            send=send,
            max_records=1,
        )
        self.assertEqual(first["acked"], 1)
        cp1 = json.loads(self.checkpoint.read_text())
        self.assertGreater(cp1["cursor"], 0)
        self.assertEqual(sent[0]["source_kind"], "audience_comment")

        second = sync.sync_once(
            self.ledger_path,
            self.checkpoint,
            send=lambda payload: receipt(),
            max_records=4,
        )
        self.assertEqual(second["acked"], 1)
        self.assertEqual(
            json.loads(self.checkpoint.read_text())["cursor"],
            self.ledger_path.stat().st_size,
        )
        self.assertEqual(
            sync.sync_once(
                self.ledger_path,
                self.checkpoint,
                send=lambda payload: receipt(),
                max_records=4,
            )["acked"],
            0,
        )

    def test_sync_failure_never_advances_cursor(self) -> None:
        def fail(_payload):
            raise sync.CognitiveEvidenceSyncError("local_server_unavailable")

        with self.assertRaisesRegex(
            sync.CognitiveEvidenceSyncError,
            "local_server_unavailable",
        ):
            sync.sync_once(
                self.ledger_path,
                self.checkpoint,
                send=fail,
                max_records=1,
            )
        self.assertFalse(self.checkpoint.exists())

        ok = sync.sync_once(
            self.ledger_path,
            self.checkpoint,
            send=lambda payload: receipt(),
            max_records=1,
        )
        self.assertEqual(ok["acked"], 1)

    def test_duplicate_structural_ack_is_safe(self) -> None:
        result = sync.sync_once(
            self.ledger_path,
            self.checkpoint,
            send=lambda payload: receipt(duplicate=True),
            max_records=1,
        )
        self.assertEqual(result["acked"], 1)
        self.assertEqual(result["stored"], 0)
        self.assertEqual(result["duplicates"], 1)

    def test_simulator_does_not_enter_social_memory_lane(self) -> None:
        cognitive = (
            ROOT / "apps" / "world-runtime" / "main_cognitive_live.py"
        ).read_text(encoding="utf-8")
        main_live = (
            ROOT / "apps" / "world-runtime" / "main_live.py"
        ).read_text(encoding="utf-8")
        self.assertIn("memory_eligible=False", cognitive)
        self.assertIn('source in {"tiktok", "youtube"}', main_live)
        self.assertIn("parent_record_key=parent_record_key", main_live)


class CognitiveEvidenceDeploymentTests(unittest.TestCase):
    def test_sync_unit_is_local_bounded_and_non_authoritative(self) -> None:
        service = (ROOT / "deploy" / "live-infinita-cognitive-evidence-sync.service").read_text()
        timer = (ROOT / "deploy" / "live-infinita-cognitive-evidence-sync.timer").read_text()
        self.assertIn("127.0.0.1", (ROOT / "apps" / "world-runtime" / "cognitive_evidence_sync.py").read_text())
        self.assertIn("IPAddressDeny=any", service)
        self.assertIn("IPAddressAllow=localhost", service)
        self.assertIn("--max-records 32", service)
        self.assertIn("OnUnitInactiveSec=30s", timer)

    def test_mobile_rollout_installs_code_units_and_timer(self) -> None:
        rollout = (ROOT / "deploy" / "apply-cognitive-memory-loop-008a.sh").read_text()
        self.assertIn("systemctl daemon-reload", rollout)
        self.assertIn("systemctl enable --now live-infinita-cognitive-evidence-sync.timer", rollout)
        self.assertIn("systemctl restart live-infinita.service", rollout)
        self.assertIn("rollback()", rollout)


if __name__ == "__main__":
    unittest.main()
