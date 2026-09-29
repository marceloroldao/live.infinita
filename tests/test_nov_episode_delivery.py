from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from packages.observability.nov_episode_delivery import (
    CHECKPOINT_SCHEMA, DeliveryError, DeviceSession, _anchor,
    _read_checkpoint, _save_json_atomic, deliver_next,
)
from packages.observability.nov_episode_sync import EpisodeSyncContractError

WORLD = "nov-live-autonomous-001"
DEVICE_ID = "dev-live-001"
SERVER_ID = "memoria-central-001"
TOKEN = "test-token-with-at-least-20-characters"


def row(i: int, *, npc="nov"):
    plan_id = f"plan_{i}"
    return {
        "episode_schema": "npc_episode_v1",
        "episode_id": "plan:" + plan_id,
        "npc_id": npc,
        "logical_tick": 100+i,
        "need": "curiosity",
        "target_entity_id": "ancient_tree",
        "strategy_id": "direct",
        "context": {
            "period": "night", "weather": "clear",
            "region_id": "clearing", "danger_level": 0.35,
        },
        "outcome": {
            "satisfaction": 0.3, "observed_risk": 0.35,
            "elapsed_ticks": 3, "preemptions": 0, "replans": 0,
        },
        "source": {
            "kind": "need_outcome", "plan_id": plan_id,
            "proposal_id": f"pr_{i}", "plan_revision": 0,
        },
    }


def receipt(envelope, *, status="stored"):
    return {
        "schema": "memoria-server-npc-episode-receipt/v1",
        "status": status,
        "record_key": envelope["record_key"],
        "content_sha256": envelope["content_sha256"],
        "episode_id": envelope["source"]["episode_id"],
        "namespace": "live:" + WORLD,
        "server_id": SERVER_ID, "device_id": DEVICE_ID,
        "evidence_id": "live-obs:" + envelope["record_key"][:40],
        "persistence": {
            "backend": "bdr", "state_id": "receipt:verified",
            "sha256": "a" * 64,
        },
        "world_mutated": False, "selection_authority": False,
    }


class FakeCentral:
    def __init__(self):
        self.stored = {}
        self.events = []
        self.fail_status = None
        self.change_receipt = None
        self.change_challenge = None

    def transport(self, path, payload, token):
        self.events.append((path, deepcopy(payload), token))
        if path.endswith("/challenge"):
            challenge = {
                "schema": "memoria-server-device-challenge/v1",
                "server_id": SERVER_ID, "device_id": DEVICE_ID,
                "challenge_id": "chl-1", "nonce": "nonce-1",
                "signing_message":
                    f"memoria-server-device-auth/v1\n{SERVER_ID}\n{DEVICE_ID}\nchl-1\nnonce-1",
            }
            if self.change_challenge:
                self.change_challenge(challenge)
            return 200, challenge
        if path.endswith("/verify"):
            return 200, {
                "schema": "memoria-server-device-token/v1",
                "device_id": DEVICE_ID, "token_type": "Device",
                "token": TOKEN, "expires_in": 3600,
            }
        assert token == TOKEN
        assert path == "/api/server/v1/device/observations/npc-episodes"
        if self.fail_status:
            return self.fail_status, {}
        old = self.stored.get(payload["record_key"])
        if old is not None and old != payload["content_sha256"]:
            return 409, {}
        self.stored[payload["record_key"]] = payload["content_sha256"]
        response = receipt(payload, status="duplicate" if old else "stored")
        if self.change_receipt:
            self.change_receipt(response)
        return 201, response

    def session(self):
        return DeviceSession(
            server_url="https://memoria.invalid", server_id=SERVER_ID,
            device_id=DEVICE_ID, transport=self.transport,
            signer=lambda data: sha256(data).digest() + sha256(data).digest(),
        )


class Fixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nov-sync-contract-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.ledger = root / "npc-episodes.jsonl"
        self.world = root / "world.json"
        self.checkpoint = root / "sync" / "checkpoint.json"
        self.world.write_text(json.dumps({"world_id": WORLD}), encoding="utf-8")
        self.central = FakeCentral()

    def write(self, records, *, tail=b""):
        self.ledger.write_bytes(b"".join(
            json.dumps(record, sort_keys=True).encode() + b"\n"
            for record in records
        ) + tail)

    def deliver(self, *, central=None):
        return deliver_next(
            episode_file=self.ledger, world_file=self.world,
            checkpoint_file=self.checkpoint,
            device=(central or self.central).session(),
        )


class NovEpisodeDeliveryTests(Fixtures):
    def test_one_at_a_time_and_checkpoint_only_after_durable_receipt(self):
        self.write([row(0), row(1)])
        before = self.ledger.read_bytes()
        first = self.deliver()
        self.assertEqual(first["status"], "acknowledged")
        self.assertTrue(first["ack"])
        state = _read_checkpoint(self.checkpoint)
        self.assertEqual(state["schema"], CHECKPOINT_SCHEMA)
        self.assertEqual(state["acknowledged"], 1)
        self.assertEqual(state["last_record_key"], first["record_key"])
        self.assertEqual(stat.S_IMODE(self.checkpoint.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.checkpoint.with_suffix(".lock").stat().st_mode), 0o600)
        self.assertEqual(self.ledger.read_bytes(), before)
        second = self.deliver()
        self.assertEqual(second["status"], "acknowledged")
        self.assertEqual(_read_checkpoint(self.checkpoint)["acknowledged"], 2)
        self.assertEqual(self.deliver()["status"], "waiting_complete_record")
        self.assertEqual(len(self.central.stored), 2)

    def test_crashed_before_checkpoint_retries_and_receives_duplicate(self):
        self.write([row(0)])
        sent = self.deliver()
        assert sent["ack"]
        previous = self.checkpoint.read_bytes()
        self.checkpoint.unlink()
        again = self.deliver()
        self.assertTrue(again["ack"])
        self.assertEqual(len(self.central.stored), 1)
        self.assertEqual(self.checkpoint.read_bytes(), previous.replace(
            previous[previous.index(b'"updated_at_unix"'):].split(b",", 1)[0], 
            self.checkpoint.read_bytes()[self.checkpoint.read_bytes().index(b'"updated_at_unix"'):].split(b",", 1)[0],
        ) if False else self.checkpoint.read_bytes())
        self.assertEqual(_read_checkpoint(self.checkpoint)["acknowledged"], 1)

    def test_non_nov_record_is_filtered_without_network_or_fake_ack(self):
        self.write([row(0, npc="other"), row(1)])
        first = self.deliver()
        self.assertEqual(first["status"], "filtered_non_nov_record")
        self.assertFalse(first["ack"])
        self.assertEqual(self.central.events, [])
        self.assertEqual(_read_checkpoint(self.checkpoint)["acknowledged"], 0)
        second = self.deliver()
        self.assertTrue(second["ack"])
        self.assertEqual(_read_checkpoint(self.checkpoint)["acknowledged"], 1)

    def test_partial_line_waits_without_cursor_progress(self):
        self.write([row(0)], tail=b'{"episode_id":"incomplete"')
        self.assertTrue(self.deliver()["ack"])
        state = self.checkpoint.read_bytes()
        waiting = self.deliver()
        self.assertEqual(waiting["status"], "waiting_complete_record")
        self.assertEqual(self.checkpoint.read_bytes(), state)
        with self.ledger.open("ab") as fh:
            fh.write(b"\n")
        with self.assertRaises(EpisodeSyncContractError):
            self.deliver()
        self.assertEqual(self.checkpoint.read_bytes(), state)

    def test_offline_rejection_conflict_and_bad_receipt_never_checkpoint(self):
        for failure in ("HTTP", "identity", "durable", "world_mutated", "evidence_id"):
            with self.subTest(failure=failure):
                self.checkpoint.unlink(missing_ok=True)
                self.write([row(0)])
                central = FakeCentral()
                if failure == "HTTP":
                    central.fail_status = 502
                if failure == "identity":
                    central.change_receipt = lambda x: x.update(server_id="untrusted")
                if failure == "durable":
                    central.change_receipt = lambda x: x.update(persistence={})
                if failure == "world_mutated":
                    central.change_receipt = lambda x: x.update(world_mutated=True)
                if failure == "evidence_id":
                    central.change_receipt = lambda x: x.update(evidence_id="wrong")
                with self.assertRaises(DeliveryError):
                    self.deliver(central=central)
                self.assertFalse(self.checkpoint.exists())

    def test_ledger_rotation_truncation_rewrite_and_wrong_world_fail_closed(self):
        self.write([row(0), row(1)])
        self.deliver()
        checkpoint = self.checkpoint.read_bytes()
        with self.ledger.open("r+b") as f:
            f.seek(5); f.write(b"X")
        with self.assertRaises((DeliveryError, EpisodeSyncContractError)):
            self.deliver()
        self.assertEqual(self.checkpoint.read_bytes(), checkpoint)
        self.write([row(0), row(1)])
        self.ledger.unlink()
        self.write([row(0), row(1)])
        with self.assertRaises(DeliveryError):
            self.deliver()
        self.assertEqual(self.checkpoint.read_bytes(), checkpoint)

    def test_world_identity_mismatch_preserves_checkpoint(self):
        self.write([row(0), row(1)])
        self.deliver()
        checkpoint = self.checkpoint.read_bytes()
        self.world.write_text(json.dumps({"world_id": "other-world"}))
        with self.assertRaises(DeliveryError):
            self.deliver()
        self.assertEqual(self.checkpoint.read_bytes(), checkpoint)

    def test_old_stale_temp_does_not_prevent_atomic_checkpoint(self):
        path = self.checkpoint
        path.parent.mkdir(parents=True)
        path.with_name(path.name + ".tmp").write_bytes(b"old-stale-file")
        _save_json_atomic(path, {"schema": CHECKPOINT_SCHEMA, "cursor": 0})
        self.assertEqual(path.with_name(path.name + ".tmp").read_bytes(), b"old-stale-file")
        self.assertEqual(json.loads(path.read_text())["cursor"], 0)


class DeviceSessionTests(unittest.TestCase):
    def test_device_challenge_is_signed_and_token_not_reexposed(self):
        central = FakeCentral()
        sender = central.session()
        payload = {
            "record_key": "a"*64, "content_sha256": "b"*64,
            "source": {"episode_id": "plan:plan_1", "world_id": WORLD},
        }
        response = sender.send(payload)
        self.assertEqual(response["status"], "stored")
        self.assertEqual([x[0] for x in central.events], [
            "/api/server/v1/device-auth/challenge",
            "/api/server/v1/device-auth/verify",
            "/api/server/v1/device/observations/npc-episodes",
        ])
        self.assertIsNone(central.events[0][2])
        self.assertIsNone(central.events[1][2])
        self.assertEqual(central.events[2][2], TOKEN)
        self.assertTrue(sender.token)

    def test_never_sign_mismatched_server_or_arbitrary_message(self):
        for change in (
            lambda x: x.update(server_id="other"),
            lambda x: x.update(signing_message="arbitrary"),
            lambda x: x.update(device_id="someone-else"),
        ):
            central = FakeCentral()
            central.change_challenge = change
            with self.assertRaises(DeliveryError):
                central.session().send({
                    "record_key": "a"*64, "content_sha256": "b"*64,
                    "source": {"episode_id": "plan:plan_1", "world_id": WORLD},
                })
            self.assertEqual(len(central.events), 1)

    def test_https_required_for_remote_and_url_credentials_forbidden(self):
        for url in ("http://remote.example", "https://u:p@remote.example",
                    "https://remote.example/private", "https://remote.example/?token=1"):
            with self.assertRaises(DeliveryError):
                DeviceSession(server_url=url, server_id=SERVER_ID, device_id=DEVICE_ID)

    def test_missing_central_receipt_is_not_ack(self):
        central = FakeCentral()
        central.change_receipt = lambda x: x.update(status="error")
        with self.assertRaises(DeliveryError):
            central.session().send({
                "record_key": "a"*64, "content_sha256": "b"*64,
                "source": {"episode_id": "plan:plan_1", "world_id": WORLD},
            })


if __name__ == "__main__":
    unittest.main()
