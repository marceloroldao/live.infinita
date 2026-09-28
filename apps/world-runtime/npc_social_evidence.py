from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from pathlib import Path
from typing import Any


class SocialEvidenceError(ValueError):
    """Evidence was absent, unverified, incomplete or contradictory."""


class NpcSocialEvidenceMemory:
    """Single-writer, append-only relationship evidence, not a friendship classifier.

    Encounters come only from the authoritative NPC need-outcome processor.
    Confirmed exchanges are resolved from an injected trusted world-event source;
    callers cannot submit arbitrary payloads as proof. Nothing in this class
    creates world entities, confirms an exchange from a comment, or lets an LLM
    select actions. The confirmed-event producer is a separate future contract.
    """

    SCHEMA = "npc_social_evidence_v1"
    EXCHANGE_SCHEMA = "social_exchange_v1"
    ACK_SCHEMA = "social_ack_v1"
    MAX_CREDIT = 0.35

    def __init__(
        self,
        path: Path,
        *,
        need_dynamics: Any | None = None,
        episodic_memory: Any | None = None,
        need_learning: Any | None = None,
        world_event_resolver: Any | None = None,
        source_need_outcomes: Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.need_dynamics = need_dynamics
        self.episodic_memory = episodic_memory
        self.need_learning = need_learning
        self.world_event_resolver = world_event_resolver
        self.source_need_outcomes = source_need_outcomes
        self._historical_reconciled = False
        self._ids: set[str] | None = None
        self._signature: tuple[int, int, int, int] | None = None

    def _file_signature(self) -> tuple[int, int, int, int] | None:
        try:
            state = self.path.stat()
        except FileNotFoundError:
            return None
        return (state.st_dev, state.st_ino, state.st_size, state.st_mtime_ns)

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        with self.path.open("rb") as fh:
            for raw in fh:
                if not raw.strip():
                    continue
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise SocialEvidenceError("invalid social evidence row")
                rows.append(value)
        return rows

    def _seen(self) -> set[str]:
        if self._ids is not None and self._signature == self._file_signature():
            return self._ids
        for _ in range(3):
            before = self._file_signature()
            ids = {str(row["evidence_id"]) for row in self.history()}
            after = self._file_signature()
            if before == after:
                self._ids, self._signature = ids, after
                return ids
        raise SocialEvidenceError("social evidence ledger changed during index rebuild")

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        with self.path.open("ab") as fh:
            fh.write(payload.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        self._signature = None
        return deepcopy(row)

    @staticmethod
    def _encounter(row: dict[str, Any]) -> dict[str, Any] | None:
        if row.get("status") != "encounter_observed" or row.get("need") != "social":
            return None
        proof = row.get("social_encounter_evidence")
        if not isinstance(proof, dict):
            return None
        npc_id = str(row.get("npc_id") or "").strip()
        peer_id = str(row.get("target_entity_id") or "").strip()
        plan_id = str(row.get("plan_id") or "").strip()
        if not all((npc_id, peer_id, plan_id)) or npc_id == peer_id:
            return None
        if (proof.get("schema") != "npc_social_encounter_evidence_v1"
                or proof.get("source") != "completed_movement_and_live_entity_snapshot"
                or proof.get("actor_entity_id") != npc_id
                or proof.get("target_entity_id") != peer_id
                or proof.get("co_present") is not True
                or proof.get("target_available") is not True
                or proof.get("social_interaction_confirmed") is not False):
            return None
        distance = proof.get("distance")
        if isinstance(distance, bool) or not isinstance(distance, (float, int)) or not math.isfinite(distance) or distance > 1.0 or distance < 0.0:
            return None
        return {
            "schema": NpcSocialEvidenceMemory.SCHEMA,
            "evidence_id": f"encounter:{plan_id}",
            "kind": "encounter",
            "npc_id": npc_id,
            "peer_entity_id": peer_id,
            "status": "observed_unconfirmed",
            "source": "npc_need_outcomes",
            "source_plan_id": plan_id,
            "confirmed": False,
            "satisfaction_delta": 0.0,
            "proof": deepcopy(proof),
        }

    def observe_encounters(self, outcomes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # Recover a completed need outcome if the service stopped between
        # its durable append and this derived relationship projection.
        if not self._historical_reconciled:
            history = getattr(self.source_need_outcomes, "history", None)
            if callable(history):
                outcomes = list(history()) + list(outcomes)
        candidates = []
        for outcome in outcomes:
            if isinstance(outcome, dict):
                evidence = self._encounter(outcome)
                if evidence is not None:
                    candidates.append(evidence)
        if not candidates:
            self._historical_reconciled = True
            return []
        processed = self._seen()
        added = []
        for row in candidates:
            evidence_id = row["evidence_id"]
            if evidence_id in processed:
                continue
            self._append(row)
            processed.add(evidence_id)
            added.append(deepcopy(row))
        self._historical_reconciled = True
        return added

    def _trusted_event(self, event_id: str) -> dict[str, Any]:
        resolver = self.world_event_resolver
        if not callable(resolver):
            raise SocialEvidenceError("trusted world event resolver unavailable")
        value = resolver(event_id)
        if not isinstance(value, dict) or value.get("event_id") != event_id:
            raise SocialEvidenceError("authoritative world event missing")
        return deepcopy(value)

    def _confirmations(self, exchange: dict[str, Any], npc_id: str, peer_id: str) -> dict[str, str]:
        exchange_id = exchange["event_id"]
        ids = {
            "npc": str(exchange.get("npc_ack_event_id") or "").strip(),
            "peer": str(exchange.get("peer_ack_event_id") or "").strip(),
        }
        if not all(ids.values()) or ids["npc"] == ids["peer"] or exchange_id in ids.values():
            raise SocialEvidenceError("distinct participant acknowledgements required")
        channel = str((exchange.get("provenance") or {}).get("channel") or "")
        source_event_id = str((exchange.get("provenance") or {}).get("source_event_id") or "")
        if channel not in {"agent", "audience"} or (channel == "audience" and not source_event_id):
            raise SocialEvidenceError("exchange provenance is incomplete")
        for role, entity_id in (("npc", npc_id), ("peer", peer_id)):
            ack = self._trusted_event(ids[role])
            if (ack.get("schema") != self.ACK_SCHEMA
                    or ack.get("kind") != "participant_ack"
                    or ack.get("exchange_event_id") != exchange_id
                    or ack.get("participant_role") != role
                    or ack.get("entity_id") != entity_id
                    or ack.get("status") != "accepted"):
                raise SocialEvidenceError("participant acknowledgement did not match")
            if channel == "audience" and role == "peer":
                if ack.get("source_event_id") != source_event_id or ack.get("binding_verified") is not True:
                    raise SocialEvidenceError("audience identity/binding proof missing")
        return ids

    def record_confirmed(self, event_id: str) -> dict[str, Any]:
        """Project an exchange already verified by the world event authority.

        This method accepts only its event ID. Three distinct records must
        resolve from the trusted event source: exchange and both participants'
        explicit acknowledgements. An audience peer additionally needs a
        verified actor binding tied to the same source event. No raw comment,
        narrator prose or single-party operator assertion qualifies.
        """
        event_id = str(event_id or "").strip()
        if not event_id:
            raise SocialEvidenceError("event id required")
        exchange = self._trusted_event(event_id)
        npc_id = str(exchange.get("npc_id") or "").strip()
        peer_id = str(exchange.get("peer_entity_id") or "").strip()
        if (exchange.get("schema") != self.EXCHANGE_SCHEMA
                or exchange.get("kind") != "social_exchange"
                or exchange.get("status") != "completed"
                or not npc_id or not peer_id or npc_id == peer_id
                or not isinstance(exchange.get("logical_tick"), int)
                or isinstance(exchange.get("logical_tick"), bool)
                or exchange["logical_tick"] < 0):
            raise SocialEvidenceError("not a completed authoritative social exchange")
        outcome = exchange.get("outcome")
        if not isinstance(outcome, dict) or outcome.get("signal") not in {"positive", "neutral", "negative"}:
            raise SocialEvidenceError("confirmed social outcome is missing")
        amount = outcome.get("observed_satisfaction_delta")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount) or not 0.0 <= amount <= self.MAX_CREDIT:
            raise SocialEvidenceError("observed satisfaction must be finite and bounded")
        if outcome["signal"] != "positive" and amount != 0:
            raise SocialEvidenceError("neutral/negative outcome cannot grant positive credit")
        acks = self._confirmations(exchange, npc_id, peer_id)
        evidence_id = f"exchange:{event_id}"
        if evidence_id in self._seen():
            for old in self.history():
                if old.get("evidence_id") == evidence_id:
                    return deepcopy(old)
            raise SocialEvidenceError("social evidence index inconsistent")
        if amount > 0 and self.need_dynamics is None:
            raise SocialEvidenceError("need dynamics required for positive credit")
        record = {
            "schema": self.SCHEMA,
            "evidence_id": evidence_id,
            "kind": "confirmed_exchange",
            "npc_id": npc_id,
            "peer_entity_id": peer_id,
            "status": "confirmed",
            "source": "authoritative_world_event",
            "source_world_event_id": event_id,
            "logical_tick": exchange["logical_tick"],
            "provenance": deepcopy(exchange.get("provenance")),
            "ack_event_ids": acks,
            "signal": outcome["signal"],
            "confirmed": True,
            "observed_satisfaction_delta": amount,
        }
        # Downstream operations are independently idempotent by the same event.
        # A crash before the final ledger append can safely replay the event.
        applied = None
        if amount > 0:
            applied = self.need_dynamics.satisfy(
                npc_id, "social", amount,
                outcome_id=evidence_id,
                metadata={"source": "confirmed_social_exchange", "world_event_id": event_id,
                          "peer_entity_id": peer_id, "ack_event_ids": deepcopy(acks)},
            )
        actual = max(0.0, float(applied["before"]) - float(applied["after"])) if applied else 0.0
        episode = None
        if self.episodic_memory is not None:
            remember = getattr(self.episodic_memory, "remember", None)
            if callable(remember):
                episode = remember(
                    episode_id=evidence_id, npc_id=npc_id,
                    logical_tick=exchange["logical_tick"], need="social",
                    target_entity_id=peer_id, strategy_id="verified_social_exchange",
                    context=exchange.get("context"), satisfaction=actual,
                    elapsed_ticks=0, source={
                        "kind": "confirmed_social_exchange", "world_event_id": event_id,
                        "ack_event_ids": deepcopy(acks), "signal": outcome["signal"],
                        "provenance": deepcopy(exchange.get("provenance")),
                    },
                )
        learning = None
        if self.need_learning is not None:
            observe = getattr(self.need_learning, "observe", None)
            if callable(observe):
                learning = observe(
                    outcome_id=evidence_id, npc_id=npc_id, need="social",
                    target_entity_id=peer_id, satisfaction=actual,
                    context=exchange.get("context"),
                )
        record["satisfaction_delta"] = actual
        record["episode_id"] = episode.get("episode_id") if isinstance(episode, dict) else None
        record["learning_outcome_id"] = learning.get("outcome_id") if isinstance(learning, dict) else None
        return self._append(record)

    def relationship(self, npc_id: str, peer_entity_id: str) -> dict[str, Any]:
        """Observed trajectory only: counters, not imposed friendship labels."""
        npc_id = str(npc_id or "").strip()
        peer_entity_id = str(peer_entity_id or "").strip()
        rows = [
            row for row in self.history()
            if row.get("npc_id") == npc_id and row.get("peer_entity_id") == peer_entity_id
        ]
        confirmed = [row for row in rows if row.get("kind") == "confirmed_exchange"]
        signals = {key: sum(row.get("signal") == key for row in confirmed)
                   for key in ("positive", "neutral", "negative")}
        return {
            "schema": "npc_social_relationship_evidence_v1",
            "npc_id": npc_id, "peer_entity_id": peer_entity_id,
            "encounters": sum(row.get("kind") == "encounter" for row in rows),
            "confirmed_exchanges": len(confirmed),
            "signals": signals,
            "cumulative_observed_satisfaction": sum(float(row.get("satisfaction_delta") or 0.0) for row in confirmed),
            "evidence_ids": [row["evidence_id"] for row in rows],
            "relation_label": None,
            "world_mutated": False,
        }
