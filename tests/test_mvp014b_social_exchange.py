from __future__ import annotations

import hashlib
import hmac
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_social_exchange import (  # noqa: E402
    NpcSocialExchangeProducer, SocialEventError, SocialEventJournal, _canonical,
)
from npc_social_evidence import NpcSocialEvidenceMemory  # noqa: E402
from npc_need_dynamics import NpcNeedDynamics  # noqa: E402
from npc_need_learning import NpcNeedLearning  # noqa: E402
from npc_episodic_memory import NpcEpisodicMemory  # noqa: E402
from tests.test_npc_need_scheduler import FakeStore  # noqa: E402
from tests.test_mvp013_social_opportunity import nov, actor  # noqa: E402
from tests.test_mvp014_social_evidence import encounter  # noqa: E402
from tests.test_simulation_clock_world_tick import FakeScheduler, SimulationClock, WorldTickRunner  # noqa: E402


KEYS = {("nov", "agent"): b"N"*32, ("friend", "agent"): b"F"*32,
        ("friend", "audience"): b"T"*32}


def receipt(role, *, exchange_id="exchange1", channel="agent", signal="positive",
            amount=0.2, actor_key=None, source_id=None, receipt_id=None):
    entity = "nov" if role == "npc" else "friend"
    source_id = source_id or ("nov:decision:1" if role == "npc" else "friend:decision:1")
    row = {
        "schema": "social_participation_receipt_v1",
        "receipt_id": receipt_id or f"{role}:receipt:1",
        "exchange_id": exchange_id,
        "encounter_evidence_id": "encounter:p1",
        "role": role,
        "entity_id": entity,
        "issuer_id": f"{entity}:authority",
        "channel": channel,
        "source_event_id": source_id,
        "actor_key": actor_key,
        "decision": "accepted",
        "outcome": {"signal": signal, "observed_satisfaction_delta": amount},
    }
    row["signature"] = hmac.new(KEYS[(entity, channel)], _canonical(row), hashlib.sha256).hexdigest()
    return row


class SocialProducerTests(unittest.TestCase):
    def make(self, path, *, keys=KEYS, binding=None, source_verified=None):
        origin = nov()
        origin["position"]["x"] = 10
        store = FakeStore([origin, actor("friend")])
        dynamics = NpcNeedDynamics(path / "needs.json", store, npc_ids=["nov"])
        dynamics.advance_tick(1)
        episodes = NpcEpisodicMemory(path / "episodes.jsonl")
        learning = NpcNeedLearning(path / "learning.json")
        evidence = NpcSocialEvidenceMemory(
            path / "evidence.jsonl", need_dynamics=dynamics,
            episodic_memory=episodes, need_learning=learning,
        )
        evidence.observe_encounters([encounter()])
        journal = SocialEventJournal(path / "social-events.jsonl")
        producer = NpcSocialExchangeProducer(
            journal, evidence, store,
            key_provider=(lambda eid, channel: keys.get((eid, channel))) if keys is not None else None,
            clock_provider=lambda: 22,
            binding_provider=binding,
            source_event_verifier=source_verified,
        )
        return producer, journal, evidence, dynamics, episodes, learning, store

    def test_two_independently_signed_agent_receipts_confirm_once(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(Path(d))
            need_before = dynamics.get_needs("nov")["social"]
            first = producer.produce(
                encounter_id="encounter:p1",
                npc_receipt=receipt("npc"),
                peer_receipt=receipt("peer"),
            )
            self.assertEqual(first["source"], "authoritative_social_event_ledger")
            self.assertEqual(first["status"], "confirmed")
            self.assertAlmostEqual(first["satisfaction_delta"], 0.2)
            self.assertEqual(len(journal._ordered), 3)
            self.assertEqual([r["kind"] for r in journal._ordered],
                             ["participant_ack", "participant_ack", "social_exchange"])
            self.assertAlmostEqual(dynamics.get_needs("nov")["social"], need_before - .2)
            self.assertEqual(len(episodes.history()), 1)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            self.assertEqual(producer.produce(
                encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                peer_receipt=receipt("peer")), first)
            self.assertEqual(len(journal._ordered), 3)
            self.assertEqual(producer.reconcile(), [])
            reopened = SocialEventJournal(journal.path)
            self.assertEqual(reopened.get(journal._ordered[-1]["event_id"])["status"], "completed")
            self.assertEqual(evidence.relationship("nov", "friend")["confirmed_exchanges"], 1)

    def test_missing_credentials_and_forged_signature_are_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, *_ = self.make(Path(d), keys=None)
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=receipt("peer"))
            self.assertFalse(journal.path.exists())
            producer.key_provider = lambda entity, channel: KEYS.get((entity, channel))
            fake = receipt("peer")
            fake["outcome"]["observed_satisfaction_delta"] = 0.3
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=fake)
            self.assertFalse(journal.path.exists())
            self.assertEqual(evidence.relationship("nov", "friend")["confirmed_exchanges"], 0)

    def test_ambiguous_or_single_party_receipts_cannot_confirm(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, *_ = self.make(Path(d))
            for bad in (
                receipt("npc"),
                receipt("peer", exchange_id="other"),
                receipt("peer", receipt_id="npc:receipt:1"),
                receipt("peer", signal="neutral", amount=0),
            ):
                with self.subTest(bad=bad["receipt_id"], exchange=bad["exchange_id"]), self.assertRaises(SocialEventError):
                    producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                     peer_receipt=bad)
            self.assertFalse(journal.path.exists())

    def test_revoked_presence_rejects_exchange_before_any_event(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(Path(d))
            store.entities["friend"]["properties"]["available_for_interaction"] = False
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=receipt("peer"))
            self.assertFalse(journal.path.exists())
            self.assertEqual(episodes.history(), [])

    def test_audience_requires_current_binding_and_verified_source_event(self):
        with tempfile.TemporaryDirectory() as d:
            binds = {"tiktok:user42": "friend"}
            verified = {"tiktok:message42"}
            producer, journal, *_ = self.make(
                Path(d), binding=binds.get,
                source_verified=lambda source_event_id, actor_key:
                    source_event_id in verified and actor_key == "tiktok:user42",
            )
            peer = receipt("peer", channel="audience", actor_key="tiktok:user42",
                           source_id="tiktok:message42")
            binds.clear()
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=peer)
            binds["tiktok:user42"] = "friend"
            verified.clear()
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=peer)
            self.assertFalse(journal.path.exists())
            verified.add("tiktok:message42")
            row = producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                   peer_receipt=peer)
            self.assertEqual(row["provenance"]["channel"], "audience")
            self.assertEqual(row["provenance"]["source_event_id"], "tiktok:message42")
            self.assertTrue(journal._ordered[1]["binding_verified"])

    def test_crash_after_first_ack_is_recoverable_with_same_receipts(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(Path(d))
            original = journal.append
            calls = 0
            def interrupted(row):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated crash")
                return original(row)
            with patch.object(journal, "append", side_effect=interrupted):
                with self.assertRaises(OSError):
                    producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                     peer_receipt=receipt("peer"))
            self.assertEqual(len(journal._ordered), 1)
            self.assertEqual(evidence.relationship("nov", "friend")["confirmed_exchanges"], 0)
            row = producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                   peer_receipt=receipt("peer"))
            self.assertEqual(row["status"], "confirmed")
            self.assertEqual(len(journal._ordered), 3)

    def test_crash_after_complete_journal_recovers_memory_without_duplicate_credit(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(Path(d))
            before = dynamics.get_needs("nov")["social"]
            with patch.object(evidence, "_append", side_effect=OSError("simulated crash")):
                with self.assertRaises(OSError):
                    producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                     peer_receipt=receipt("peer"))
            self.assertEqual(len(journal._ordered), 3)
            self.assertEqual(evidence.relationship("nov", "friend")["confirmed_exchanges"], 0)
            self.assertAlmostEqual(dynamics.get_needs("nov")["social"], before - .2)
            self.assertEqual(len(episodes.history()), 1)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            replayed = producer.reconcile()
            self.assertEqual(len(replayed), 1)
            self.assertEqual(producer.reconcile(), [])
            self.assertEqual(len(episodes.history()), 1)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            self.assertAlmostEqual(dynamics.get_needs("nov")["social"], before - .2)

    def test_reconciliation_does_not_rescan_unchanged_history_each_tick(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, *_ = self.make(Path(d))
            self.assertEqual(producer.reconcile(), [])
            with patch.object(journal, "completed_exchanges",
                              side_effect=AssertionError("unexpected full event replay")):
                self.assertEqual(producer.reconcile(), [])

    def test_peer_capability_is_explicit_not_inferred_from_text_or_type(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(Path(d))
            store.entities["friend"]["properties"]["interaction_capabilities"] = "social"
            with self.assertRaises(SocialEventError):
                producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                                 peer_receipt=receipt("peer"))
            self.assertFalse(journal.path.exists())

    def test_world_tick_reconciles_authoritative_exchange_after_interruption(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            producer, journal, evidence, dynamics, episodes, learning, store = self.make(root)
            with patch.object(evidence, "_append", side_effect=OSError("simulated crash")):
                with self.assertRaises(OSError):
                    producer.produce(encounter_id="encounter:p1",
                                     npc_receipt=receipt("npc"), peer_receipt=receipt("peer"))
            runner = WorldTickRunner(
                SimulationClock(root / "clock.json"), FakeScheduler(),
                npc_social_evidence=evidence,
                npc_social_exchange_producer=producer,
            )
            result = runner.tick()
            self.assertTrue(result["advanced"])
            self.assertEqual(len(result["npc_social_exchanges"]), 1)
            self.assertEqual(result["npc_social_exchanges"][0]["status"], "confirmed")
            self.assertEqual(result["npc_social_exchanges"][0]["satisfaction_delta"],
                             evidence.relationship("nov","friend")["cumulative_observed_satisfaction"])
            self.assertEqual(runner.tick()["npc_social_exchanges"], [])
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)

    def test_chain_detects_external_tampering_and_conflicting_event(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, *_ = self.make(Path(d))
            producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                             peer_receipt=receipt("peer"))
            existing = journal.get(journal._ordered[-1]["event_id"])
            altered = dict(existing)
            altered["outcome"] = {"signal": "negative", "observed_satisfaction_delta": 0}
            with self.assertRaises(SocialEventError):
                journal.append(altered)
            lines = journal.path.read_text().splitlines()
            first = json.loads(lines[0])
            first["entity_id"] = "stranger"
            lines[0] = json.dumps(first)
            journal.path.write_text("\n".join(lines)+"\n")
            with self.assertRaises(SocialEventError):
                SocialEventJournal(journal.path)

    def test_receipt_cannot_be_reused_across_exchange_ids(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, *_ = self.make(Path(d))
            producer.produce(encounter_id="encounter:p1", npc_receipt=receipt("npc"),
                             peer_receipt=receipt("peer"))
            with self.assertRaises(SocialEventError):
                producer.produce(
                    encounter_id="encounter:p1",
                    npc_receipt=receipt("npc", exchange_id="exchange2"),
                    peer_receipt=receipt("peer", exchange_id="exchange2"),
                )
            self.assertEqual(len(journal._ordered), 3)

    def test_negative_exchange_keeps_social_need_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            producer, journal, evidence, dynamics, *_ = self.make(Path(d))
            before = dynamics.get_needs("nov")["social"]
            row = producer.produce(
                encounter_id="encounter:p1",
                npc_receipt=receipt("npc", signal="negative", amount=0),
                peer_receipt=receipt("peer", signal="negative", amount=0),
            )
            self.assertEqual(row["signal"], "negative")
            self.assertEqual(row["satisfaction_delta"], 0)
            self.assertEqual(dynamics.get_needs("nov")["social"], before)
            self.assertEqual(evidence.relationship("nov","friend")["signals"]["negative"], 1)


if __name__ == "__main__":
    unittest.main()
