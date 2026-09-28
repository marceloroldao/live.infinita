from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable

from npc_social_evidence import NpcSocialEvidenceMemory, SocialEvidenceError


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


class SocialEventError(ValueError):
    pass


class SocialEventJournal:
    """Single-writer fsynced social-event chain, separate from world-state deltas.

    This ledger is an internally trusted event source, NOT a public event inbox.
    Its hash chain detects partial/corrupted history but is not a digital signature.
    """

    GENESIS = "0" * 64

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rows: dict[str, dict[str, Any]] = {}
        self._ordered: list[dict[str, Any]] = []
        self._signature: tuple[int, int, int, int] | None = None
        self._load()

    def _stat(self):
        try:
            s = self.path.stat()
            return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns
        except FileNotFoundError:
            return None

    def _load(self):
        rows: dict[str, dict[str, Any]] = {}
        ordered = []
        previous = self.GENESIS
        if self.path.exists():
            with self.path.open("rb") as fh:
                for raw in fh:
                    if not raw.strip():
                        continue
                    try:
                        row = json.loads(raw)
                        signed = {key: value for key, value in row.items() if key != "chain_hash"}
                        expected = hashlib.sha256(b"social-event-v1\0" + _canonical(signed)).hexdigest()
                    except (ValueError, TypeError, KeyError, AttributeError) as exc:
                        raise SocialEventError("invalid social event record") from exc
                    event_id = str(row.get("event_id") or "")
                    if (not event_id or event_id in rows
                            or row.get("sequence") != len(ordered) + 1
                            or row.get("previous_hash") != previous
                            or not hmac.compare_digest(str(row.get("chain_hash") or ""), expected)):
                        raise SocialEventError("social event hash-chain or identity mismatch")
                    rows[event_id] = row
                    ordered.append(row)
                    previous = expected
        self._rows, self._ordered = rows, ordered
        self._signature = self._stat()

    def _current(self):
        if self._signature != self._stat():
            self._load()

    def get(self, event_id: str) -> dict[str, Any] | None:
        self._current()
        row = self._rows.get(str(event_id))
        return deepcopy(row) if row is not None else None

    def completed_exchanges(self) -> list[str]:
        self._current()
        return [
            row["event_id"] for row in self._ordered
            if row.get("schema") == "social_exchange_v1"
            and row.get("kind") == "social_exchange"
            and row.get("status") == "completed"
        ]

    def receipt_used_elsewhere(self, receipt_id: str, exchange_id: str) -> bool:
        self._current()
        return any(
            row.get("receipt_id") == receipt_id and row.get("exchange_id") != exchange_id
            for row in self._ordered
        )

    def source_event_used_elsewhere(self, receipt: dict[str, Any], exchange_id: str) -> bool:
        self._current()
        return any(
            row.get("kind") == "participant_ack"
            and row.get("entity_id") == receipt["entity_id"]
            and row.get("channel") == receipt["channel"]
            and row.get("source_event_id") == receipt["source_event_id"]
            and row.get("exchange_id") != exchange_id
            for row in self._ordered
        )

    def append(self, row: dict[str, Any]) -> dict[str, Any]:
        self._current()
        event_id = str(row.get("event_id") or "").strip()
        if not event_id:
            raise SocialEventError("event_id required")
        original = deepcopy(row)
        original.pop("sequence", None)
        original.pop("previous_hash", None)
        original.pop("chain_hash", None)
        old = self._rows.get(event_id)
        if old is not None:
            equivalent = {k: v for k, v in old.items() if k not in {"sequence", "previous_hash", "chain_hash"}}
            if equivalent != original:
                raise SocialEventError("conflicting idempotent social event")
            return deepcopy(old)
        previous = self._ordered[-1]["chain_hash"] if self._ordered else self.GENESIS
        record = {
            **original, "sequence": len(self._ordered) + 1,
            "previous_hash": previous,
        }
        record["chain_hash"] = hashlib.sha256(b"social-event-v1\0" + _canonical(record)).hexdigest()
        with self.path.open("ab") as fh:
            fh.write(_canonical(record) + b"\n")
            fh.flush()
            os.fsync(fh.fileno())
        self._rows[event_id] = record
        self._ordered.append(record)
        self._signature = self._stat()
        return deepcopy(record)


class NpcSocialExchangeProducer:
    """Produces signed, reciprocal social exchanges from already-observed encounters.

    Caller must be inside the authorized Single Writer, never a public request.
    Key provider returns a separately provisioned secret for each entity/source.
    This class does not sign, mint a participant receipt, or trust a client flag.
    """

    RECEIPT_SCHEMA = "social_participation_receipt_v1"

    def __init__(
        self,
        journal: SocialEventJournal,
        social_evidence: NpcSocialEvidenceMemory,
        store: Any,
        *,
        key_provider: Callable[[str, str], bytes | None] | None = None,
        clock_provider: Callable[[], int] | None = None,
        binding_provider: Callable[[str], str | None] | None = None,
        source_event_verifier: Callable[[str, str], bool] | None = None,
    ):
        self.journal = journal
        self.social_evidence = social_evidence
        self.store = store
        self.key_provider = key_provider
        self.clock_provider = clock_provider
        self.binding_provider = binding_provider
        self.source_event_verifier = source_event_verifier
        self.social_evidence.world_event_resolver = self.journal.get
        self._reconciled_signature: tuple[Any, Any] | None = None

    @staticmethod
    def _event_id(kind: str, exchange_id: str) -> str:
        digest = hashlib.sha256(exchange_id.encode("utf-8")).hexdigest()
        return f"soc_{kind}:{digest}"

    def _verify_receipt(self, receipt: dict[str, Any], *, role: str, entity_id: str,
                        encounter_id: str, exchange_id: str) -> bytes:
        if not isinstance(receipt, dict):
            raise SocialEventError("signed participant receipt required")
        issuer = str(receipt.get("issuer_id") or "")
        source = str(receipt.get("channel") or "")
        source_id = str(receipt.get("source_event_id") or "")
        receipt_id = str(receipt.get("receipt_id") or "")
        signature = receipt.get("signature")
        expected_fields = {
            "schema", "receipt_id", "exchange_id", "encounter_evidence_id",
            "role", "entity_id", "issuer_id", "channel", "source_event_id",
            "actor_key", "decision", "outcome", "signature",
        }
        if (set(receipt) != expected_fields
                or receipt.get("schema") != self.RECEIPT_SCHEMA
                or receipt.get("role") != role
                or receipt.get("entity_id") != entity_id
                or receipt.get("encounter_evidence_id") != encounter_id
                or receipt.get("exchange_id") != exchange_id
                or receipt.get("decision") != "accepted"
                or not issuer or not source_id or not receipt_id or len(receipt_id) > 160
                or len(issuer) > 200 or len(source_id) > 200
                or len(str(receipt.get("actor_key") or "")) > 200
                or source not in {"agent", "audience"}
                or (role == "npc" and source != "agent")
                or not isinstance(signature, str) or len(signature) != 64):
            raise SocialEventError("invalid participant receipt contract")
        if source == "agent" and receipt.get("actor_key") is not None:
            raise SocialEventError("agent receipt cannot claim audience actor")
        if source == "audience":
            actor_key = str(receipt.get("actor_key") or "")
            if (role != "peer" or not actor_key
                    or not callable(self.binding_provider)
                    or self.binding_provider(actor_key) != entity_id
                    or not callable(self.source_event_verifier)
                    or self.source_event_verifier(source_id, actor_key) is not True):
                raise SocialEventError("audience origin or current binding unverified")
        key = self.key_provider(entity_id, source) if callable(self.key_provider) else None
        if not isinstance(key, bytes) or len(key) < 32:
            raise SocialEventError("entity signing key not provisioned")
        payload = {name: value for name, value in receipt.items() if name != "signature"}
        try:
            expected = hmac.new(key, _canonical(payload), hashlib.sha256).hexdigest()
        except (TypeError, ValueError) as exc:
            raise SocialEventError("malformed signed payload") from exc
        if not hmac.compare_digest(signature, expected):
            raise SocialEventError("invalid participant signature")
        return key

    def _encounter(self, encounter_id: str) -> dict[str, Any]:
        rows = [
            r for r in self.social_evidence.history()
            if r.get("evidence_id") == encounter_id
            and r.get("kind") == "encounter"
            and r.get("status") == "observed_unconfirmed"
            and r.get("confirmed") is False
        ]
        if len(rows) != 1:
            raise SocialEventError("verified encounter evidence required")
        return rows[0]

    def _present(self, npc_id: str, peer_id: str):
        refresher = getattr(self.store, "refresh_manifest", None)
        if callable(refresher):
            refresher()  # cross-process world writes may move an entity to another region
        getter = getattr(self.store, "get_entity", None)
        if not callable(getter):
            raise SocialEventError("authoritative entity store unavailable")
        npc, peer = getter(npc_id), getter(peer_id)
        if not isinstance(npc, dict) or not isinstance(peer, dict):
            raise SocialEventError("participant entity no longer present")
        if npc.get("region_id") != peer.get("region_id"):
            raise SocialEventError("participants no longer co-present")
        properties = peer.get("properties") if isinstance(peer.get("properties"), dict) else {}
        capabilities = properties.get("interaction_capabilities")
        if (not isinstance(capabilities, list) or "social" not in capabilities
                or properties.get("available_for_interaction") is not True):
            raise SocialEventError("peer no longer available")
        try:
            xy = lambda entity: (float(entity["position"]["x"]), float(entity["position"]["y"]))
            distance = math.dist(xy(npc), xy(peer))
        except (TypeError, ValueError, KeyError, OverflowError) as exc:
            raise SocialEventError("position unavailable") from exc
        if not math.isfinite(distance) or distance > 1.0:
            raise SocialEventError("participants not within encounter distance")
        return npc, peer

    def produce(self, *, encounter_id: str, npc_receipt: dict[str, Any],
                peer_receipt: dict[str, Any]) -> dict[str, Any]:
        encounter_id = str(encounter_id or "").strip()
        if not encounter_id.startswith("encounter:"):
            raise SocialEventError("encounter id required")
        encounter = self._encounter(encounter_id)
        npc_id, peer_id = encounter["npc_id"], encounter["peer_entity_id"]
        exchange_id = str(npc_receipt.get("exchange_id") or "") if isinstance(npc_receipt, dict) else ""
        if not exchange_id or len(exchange_id) > 160:
            raise SocialEventError("exchange id required")
        npc_key = self._verify_receipt(npc_receipt, role="npc", entity_id=npc_id,
                                       encounter_id=encounter_id, exchange_id=exchange_id)
        peer_key = self._verify_receipt(peer_receipt, role="peer", entity_id=peer_id,
                                        encounter_id=encounter_id, exchange_id=exchange_id)
        if hmac.compare_digest(npc_key, peer_key):
            raise SocialEventError("independent signing credentials required")
        if (npc_receipt["receipt_id"] == peer_receipt["receipt_id"]
                or npc_receipt["source_event_id"] == peer_receipt["source_event_id"]
                or npc_receipt["outcome"] != peer_receipt["outcome"]):
            raise SocialEventError("receipts are not independent and concordant")
        for receipt in (npc_receipt, peer_receipt):
            if self.journal.receipt_used_elsewhere(receipt["receipt_id"], exchange_id):
                raise SocialEventError("participant receipt was already used elsewhere")
            if self.journal.source_event_used_elsewhere(receipt, exchange_id):
                raise SocialEventError("source decision/event was already used elsewhere")
        outcome = npc_receipt["outcome"]
        if not isinstance(outcome, dict) or set(outcome) != {"signal", "observed_satisfaction_delta"}:
            raise SocialEventError("observed exchange outcome invalid")
        signal = outcome.get("signal")
        amount = outcome.get("observed_satisfaction_delta")
        if (signal not in {"positive", "neutral", "negative"}
                or isinstance(amount, bool) or not isinstance(amount, (int, float))
                or not math.isfinite(amount) or not 0 <= amount <= .35
                or (signal != "positive" and amount != 0)):
            raise SocialEventError("outcome and satisfaction are not concordant")
        event_id = self._event_id("exchange", exchange_id)
        npc_ack_id = self._event_id("ack_npc", exchange_id)
        peer_ack_id = self._event_id("ack_peer", exchange_id)
        old = self.journal.get(event_id)
        if old is None:
            npc, _ = self._present(npc_id, peer_id)
            tick = self.clock_provider() if callable(self.clock_provider) else None
            if isinstance(tick, bool) or not isinstance(tick, int) or tick < 0:
                raise SocialEventError("trusted logical clock unavailable")
            context = {"region_id": str(npc["region_id"])}
        else:
            tick = old["logical_tick"]
            context = old.get("context") or {}
        for role, receipt, ack_id in (
            ("npc", npc_receipt, npc_ack_id), ("peer", peer_receipt, peer_ack_id),
        ):
            ack = {
                "schema": "social_ack_v1",
                "event_id": ack_id,
                "kind": "participant_ack",
                "exchange_event_id": event_id,
                "exchange_id": exchange_id,
                "encounter_evidence_id": encounter_id,
                "participant_role": role,
                "entity_id": receipt["entity_id"],
                "status": "accepted",
                "receipt_id": receipt["receipt_id"],
                "issuer_id": receipt["issuer_id"],
                "channel": receipt["channel"],
                "source_event_id": receipt["source_event_id"],
                "binding_verified": receipt["channel"] == "audience",
                "signature_fingerprint": hashlib.sha256(receipt["signature"].encode()).hexdigest(),
            }
            self.journal.append(ack)
        provenance = {
            "channel": peer_receipt["channel"],
            "source_event_id": peer_receipt["source_event_id"],
            "encounter_evidence_id": encounter_id,
            "npc_receipt_id": npc_receipt["receipt_id"],
            "peer_receipt_id": peer_receipt["receipt_id"],
        }
        exchange = {
            "schema": "social_exchange_v1",
            "event_id": event_id,
            "kind": "social_exchange",
            "exchange_id": exchange_id,
            "status": "completed",
            "npc_id": npc_id,
            "peer_entity_id": peer_id,
            "logical_tick": tick,
            "npc_ack_event_id": npc_ack_id,
            "peer_ack_event_id": peer_ack_id,
            "provenance": provenance,
            "outcome": deepcopy(outcome),
            "context": context,
        }
        self.journal.append(exchange)
        return self.social_evidence.record_confirmed(event_id)

    def reconcile(self) -> list[dict[str, Any]]:
        """Recover completed exchanges after process interruption; no unsigned input."""
        self.journal._current()
        signature = (self.journal._signature, self.social_evidence._file_signature())
        if self._reconciled_signature == signature:
            return []
        seen = self.social_evidence._seen()
        recovered = [
            self.social_evidence.record_confirmed(eid)
            for eid in self.journal.completed_exchanges()
            if f"exchange:{eid}" not in seen
        ]
        self._reconciled_signature = (
            self.journal._signature, self.social_evidence._file_signature(),
        )
        return recovered
