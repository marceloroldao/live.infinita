from __future__ import annotations

import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_social_evidence import NpcSocialEvidenceMemory, SocialEvidenceError  # noqa: E402
from npc_need_dynamics import NpcNeedDynamics  # noqa: E402
from npc_need_learning import NpcNeedLearning  # noqa: E402
from npc_episodic_memory import NpcEpisodicMemory  # noqa: E402
from tests.test_npc_need_scheduler import FakeStore  # noqa: E402
from tests.test_mvp013_social_opportunity import nov, actor  # noqa: E402
from tests.test_simulation_clock_world_tick import FakeScheduler, SimulationClock, WorldTickRunner  # noqa: E402


def encounter(*, plan_id="p1", peer_id="friend", valid=True):
    return {
        "need": "social", "status": "encounter_observed",
        "plan_id": plan_id, "npc_id": "nov", "target_entity_id": peer_id,
        "social_encounter_evidence": {
            "schema": "npc_social_encounter_evidence_v1",
            "actor_entity_id": "nov", "target_entity_id": peer_id,
            "co_present": valid, "target_available": True,
            "social_interaction_confirmed": False, "distance": 0.2,
            "source": "completed_movement_and_live_entity_snapshot",
        },
    }


def exchange_records(event_id="evt_12", *, signal="positive", amount=0.2, channel="agent"):
    source = {"channel": channel}
    if channel == "audience":
        source["source_event_id"] = "tiktok:msg_42"
    records = {
        event_id: {
            "schema": "social_exchange_v1", "event_id": event_id,
            "kind": "social_exchange", "status": "completed",
            "npc_id": "nov", "peer_entity_id": "friend",
            "logical_tick": 12, "provenance": source,
            "npc_ack_event_id": "ack_nov", "peer_ack_event_id": "ack_friend",
            "outcome": {"signal": signal, "observed_satisfaction_delta": amount},
            "context": {"period": "day", "region_id": "clearing", "weather": "clear"},
        },
        "ack_nov": {
            "schema": "social_ack_v1", "event_id": "ack_nov",
            "kind": "participant_ack", "exchange_event_id": event_id,
            "participant_role": "npc", "entity_id": "nov", "status": "accepted",
        },
        "ack_friend": {
            "schema": "social_ack_v1", "event_id": "ack_friend",
            "kind": "participant_ack", "exchange_event_id": event_id,
            "participant_role": "peer", "entity_id": "friend", "status": "accepted",
            "source_event_id": "tiktok:msg_42", "binding_verified": True,
        },
    }
    return records


class SocialEvidenceMemoryTests(unittest.TestCase):
    def make(self, root, events=None):
        store = FakeStore([nov(), actor("friend")])
        needs = NpcNeedDynamics(root / "needs.json", store, npc_ids=["nov"])
        needs.advance_tick(1)
        episodes = NpcEpisodicMemory(root / "episodes.jsonl")
        learning = NpcNeedLearning(root / "learning.json")
        memory = NpcSocialEvidenceMemory(
            root / "social.jsonl", need_dynamics=needs,
            episodic_memory=episodes, need_learning=learning,
            world_event_resolver=(events.get if events is not None else None),
        )
        return memory, needs, episodes, learning

    def test_encounter_is_one_durable_weak_relation_without_reward(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory, needs, episodes, learning = self.make(root)
            before = needs.get_needs("nov")["social"]
            first = memory.observe_encounters([encounter(), encounter(), encounter(valid=False)])
            self.assertEqual(len(first), 1)
            self.assertEqual(first[0]["kind"], "encounter")
            self.assertFalse(first[0]["confirmed"])
            self.assertEqual(memory.observe_encounters([encounter()]), [])
            restart = NpcSocialEvidenceMemory(root / "social.jsonl")
            self.assertEqual(restart.observe_encounters([encounter()]), [])
            relation = restart.relationship("nov", "friend")
            self.assertEqual(relation["encounters"], 1)
            self.assertEqual(relation["confirmed_exchanges"], 0)
            self.assertIsNone(relation["relation_label"])
            self.assertEqual(relation["cumulative_observed_satisfaction"], 0)
            self.assertEqual(needs.get_needs("nov")["social"], before)
            self.assertEqual(episodes.history(), [])
            self.assertIsNone(learning.stats("nov", "social", "friend"))

    def test_crash_gap_reconciles_durable_need_outcomes_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            class HistoricalOutcomes:
                def history(self):
                    return [encounter()]
            memory, _, _, _ = self.make(root)
            recovered = NpcSocialEvidenceMemory(
                root / "social.jsonl", source_need_outcomes=HistoricalOutcomes(),
            )
            self.assertEqual(len(recovered.observe_encounters([])), 1)
            self.assertEqual(recovered.observe_encounters([]), [])
            again = NpcSocialEvidenceMemory(
                root / "social.jsonl", source_need_outcomes=HistoricalOutcomes(),
            )
            self.assertEqual(again.observe_encounters([]), [])
            self.assertEqual(again.relationship("nov", "friend")["encounters"], 1)

    def test_world_tick_projects_authoritative_encounter_without_rewrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory, _, _, _ = self.make(root)
            class Completed:
                def process_completed(self):
                    return [encounter()]
            runner = WorldTickRunner(
                SimulationClock(root / "clock.json"),
                FakeScheduler(),
                npc_need_outcomes=Completed(),
                npc_social_evidence=memory,
            )
            first = runner.tick()
            self.assertEqual(len(first["npc_social_evidence"]), 1)
            self.assertEqual(first["npc_social_evidence"][0]["kind"], "encounter")
            self.assertFalse(first["npc_social_evidence"][0]["confirmed"])
            second = runner.tick()
            self.assertEqual(second["npc_social_evidence"], [])
            self.assertEqual(memory.relationship("nov", "friend")["encounters"], 1)

    def test_forged_and_unverified_encounters_do_not_enter_relationship(self):
        with tempfile.TemporaryDirectory() as directory:
            memory, _, _, _ = self.make(Path(directory))
            forged = [
                {"need": "social", "status": "completed", "plan_id": "a"},
                encounter(valid=False),
                {**encounter(), "target_entity_id": "other"},
                {**encounter(), "plan_id": ""},
                {**encounter(), "social_encounter_evidence": {
                    **encounter()["social_encounter_evidence"],
                    "social_interaction_confirmed": True,
                }},
                {**encounter(), "social_encounter_evidence": {
                    **encounter()["social_encounter_evidence"], "distance": float("nan"),
                }},
            ]
            self.assertEqual(memory.observe_encounters(forged), [])
            self.assertEqual(memory.history(), [])

    def test_confirmed_exchange_requires_trusted_source_and_two_matching_acks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            memory, needs, _, _ = self.make(root)
            before = needs.get_needs("nov")["social"]
            with self.assertRaises(SocialEvidenceError):
                memory.record_confirmed("evt_12")
            events = exchange_records()
            memory.world_event_resolver = events.get
            events["ack_friend"]["entity_id"] = "stranger"
            with self.assertRaises(SocialEvidenceError):
                memory.record_confirmed("evt_12")
            events["ack_friend"]["entity_id"] = "friend"
            events.pop("ack_nov")
            with self.assertRaises(SocialEvidenceError):
                memory.record_confirmed("evt_12")
            self.assertEqual(needs.get_needs("nov")["social"], before)
            self.assertEqual(memory.history(), [])

    def test_positive_exchange_reinforces_only_after_both_acks_and_replays_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = exchange_records()
            memory, needs, episodes, learning = self.make(root, events)
            memory.observe_encounters([encounter()])
            before = needs.get_needs("nov")["social"]
            first = memory.record_confirmed("evt_12")
            self.assertEqual(first["kind"], "confirmed_exchange")
            self.assertEqual(first["status"], "confirmed")
            self.assertAlmostEqual(first["satisfaction_delta"], 0.2)
            self.assertAlmostEqual(needs.get_needs("nov")["social"], before - 0.2)
            self.assertEqual(len(episodes.history()), 1)
            self.assertEqual(episodes.history()[0]["source"]["world_event_id"], "evt_12")
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            self.assertEqual(memory.record_confirmed("evt_12"), first)
            restarted = NpcSocialEvidenceMemory(
                root / "social.jsonl", need_dynamics=needs,
                episodic_memory=episodes, need_learning=learning,
                world_event_resolver=events.get,
            )
            self.assertEqual(restarted.record_confirmed("evt_12"), first)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            self.assertEqual(restarted.relationship("nov", "friend")["encounters"], 1)
            relation = restarted.relationship("nov", "friend")
            self.assertEqual(relation["confirmed_exchanges"], 1)
            self.assertEqual(relation["signals"]["positive"], 1)
            self.assertIsNone(relation["relation_label"])
            self.assertFalse(relation["world_mutated"])

    def test_audience_exchange_rejects_unbound_or_unmatched_source(self):
        with tempfile.TemporaryDirectory() as directory:
            events = exchange_records(channel="audience")
            memory, needs, _, _ = self.make(Path(directory), events)
            before = needs.get_needs("nov")["social"]
            events["ack_friend"]["binding_verified"] = False
            with self.assertRaises(SocialEvidenceError):
                memory.record_confirmed("evt_12")
            events["ack_friend"]["binding_verified"] = True
            events["ack_friend"]["source_event_id"] = "different"
            with self.assertRaises(SocialEvidenceError):
                memory.record_confirmed("evt_12")
            events["ack_friend"]["source_event_id"] = "tiktok:msg_42"
            self.assertEqual(memory.record_confirmed("evt_12")["provenance"]["channel"], "audience")
            self.assertAlmostEqual(needs.get_needs("nov")["social"], before - 0.2)

    def test_negative_or_neutral_does_not_reduce_need(self):
        for signal in ("negative", "neutral"):
            with self.subTest(signal=signal), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                events = exchange_records(signal=signal, amount=0)
                memory, needs, episodes, _ = self.make(root, events)
                before = needs.get_needs("nov")["social"]
                row = memory.record_confirmed("evt_12")
                self.assertEqual(row["satisfaction_delta"], 0.0)
                self.assertEqual(needs.get_needs("nov")["social"], before)
                self.assertEqual(episodes.history()[0]["source"]["signal"], signal)
                self.assertEqual(memory.relationship("nov", "friend")["signals"][signal], 1)
                events["evt_12"]["outcome"]["observed_satisfaction_delta"] = 0.1
                # A separate event with contradictory non-positive credit must fail.
                events["evt_12"]["event_id"] = "evt_13"
                with self.assertRaises(SocialEvidenceError):
                    memory.record_confirmed("evt_12")

    def test_invalid_credit_and_single_ack_never_write(self):
        for amount in (float("nan"), -0.1, 0.36, True):
            with self.subTest(amount=amount), tempfile.TemporaryDirectory() as directory:
                events = exchange_records(amount=amount)
                memory, needs, _, _ = self.make(Path(directory), events)
                before = needs.get_needs("nov")["social"]
                with self.assertRaises(SocialEvidenceError):
                    memory.record_confirmed("evt_12")
                self.assertEqual(memory.history(), [])
                self.assertEqual(needs.get_needs("nov")["social"], before)

    def test_crash_after_need_credit_recovers_exactly_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            events = exchange_records()
            memory, needs, episodes, learning = self.make(root, events)
            before = needs.get_needs("nov")["social"]
            with patch.object(memory, "_append", side_effect=OSError("simulated interruption")):
                with self.assertRaises(OSError):
                    memory.record_confirmed("evt_12")
            self.assertEqual(memory.history(), [])
            self.assertAlmostEqual(needs.get_needs("nov")["social"], before - 0.2)
            self.assertEqual(len(episodes.history()), 1)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            resumed = memory.record_confirmed("evt_12")
            self.assertAlmostEqual(resumed["satisfaction_delta"], 0.2)
            self.assertEqual(learning.stats("nov", "social", "friend")["count"], 1)
            self.assertAlmostEqual(needs.get_needs("nov")["social"], before - 0.2)


if __name__ == "__main__":
    unittest.main()
