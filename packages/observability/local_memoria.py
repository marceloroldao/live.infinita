"""Local-only projection of confirmed Nov episodes into the REAL Memoria.ia RC2 EvidenceCore.

This adapter intentionally imports memoria_resolutiva at execution time. It is not
a replacement memory engine; neither the narrator nor a remote service writes
these observations. The original episode ledger stays authoritative.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
from typing import Any

from packages.observability.nov_episode_sync import (
    EpisodeSyncContractError, observation_envelope, preview_episode_batch,
)

LOCAL_SCHEMA = "live-infinita-local-memoria-checkpoint/v1"
LOCAL_PROVENANCE = "live.infinita:npc_episode_v1"
PINNED_MEMORIA_COMMIT = "e38f27b639bec1cfcb83694c1418a4d01f250ffd"
CHECKPOINT_NAME = "checkpoint.json"


class LocalMemoriaError(ValueError):
    """Fail closed rather than advancing a local checkpoint without persistence."""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _anchor(ledger_path: Path, cursor: int) -> str:
    if cursor < 0:
        raise LocalMemoriaError("invalid_local_cursor")
    with ledger_path.open("rb") as source:
        source.seek(0, os.SEEK_END)
        if cursor > source.tell():
            raise LocalMemoriaError("ledger_truncated_after_checkpoint")
        source.seek(max(0, cursor - 4096))
        return sha256(source.read(min(cursor, 4096))).hexdigest()


def _load_checkpoint(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        if path.stat().st_size > 8192:
            raise LocalMemoriaError("oversized_local_checkpoint")
        row = json.loads(path.read_text("utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, LocalMemoriaError):
            raise
        raise LocalMemoriaError("invalid_local_checkpoint") from exc
    if not isinstance(row, dict) or row.get("schema") != LOCAL_SCHEMA:
        raise LocalMemoriaError("invalid_local_checkpoint")
    for key in ("world_id", "ledger_identity", "cursor", "anchor_sha256", "edge_count", "memoria_receipt"):
        if key not in row:
            raise LocalMemoriaError("incomplete_local_checkpoint")
    if (isinstance(row["cursor"], bool) or not isinstance(row["cursor"], int) or row["cursor"] < 0
            or isinstance(row["edge_count"], bool) or not isinstance(row["edge_count"], int) or row["edge_count"] < 0
            or not isinstance(row["memoria_receipt"], dict)):
        raise LocalMemoriaError("invalid_local_checkpoint")
    return row


def _durable_write_json(path: Path, payload: dict[str, Any]) -> None:
    raw = _canonical(payload).encode("utf-8") + b"\n"
    temp = path.with_name(path.name + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temp.exists():
            temp.unlink()


@dataclass(frozen=True)
class Relation:
    subject: str
    predicate: str
    object: str
    evidence_id: str
    source_text: str
    provenance: str
    origin: str
    namespace: str
    epoch: int


def _relations(envelope: dict[str, Any]) -> tuple[Relation, ...]:
    source = envelope["source"]
    obs = envelope["observation"]
    key = envelope["record_key"]
    world_id = source["world_id"]
    namespace = "live:" + world_id
    eid = "live-obs:" + key[:40]
    episode_node = "live:episode:" + eid
    origin = "live.infinita:" + world_id
    # source_text stores the typed canonical envelope; no synthetic chat text.
    source_text = _canonical({k: v for k, v in envelope.items() if k != "content_sha256"})
    prefix = (episode_node, source_text, origin, namespace, obs["logical_tick"])
    targets = [
        ("observed_experience", "live:entity:" + world_id + ":nov", "experience"),
    ]
    if obs["target_entity_id"] is not None:
        targets.append(("experienced_target", "live:entity:" + world_id + ":" + obs["target_entity_id"], "target"))
    if obs["need"] is not None:
        targets.append(("experienced_need", "live:need:" + world_id + ":" + obs["need"], "need"))
    if obs["strategy_id"] is not None:
        targets.append(("experienced_strategy", "live:strategy:" + world_id + ":" + obs["strategy_id"], "strategy"))
    return tuple(Relation(prefix[0], predicate, obj, eid + ":" + suffix,
                          prefix[1], LOCAL_PROVENANCE, prefix[2], prefix[3], prefix[4])
                 for predicate, obj, suffix in targets)


def _edge_matches(edge: Any, expected: Relation) -> bool:
    return all(getattr(edge, key) == getattr(expected, key) for key in Relation.__dataclass_fields__)


def sync_once(
    ledger_path: Path,
    world_path: Path,
    local_dir: Path,
    *,
    limit: int = 8,
) -> dict[str, Any]:
    """At most one bounded batch; checkpoint AFTER a real Memoria.ia save()."""
    from memoria_resolutiva.product_evidence import ProductEvidenceService

    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(local_dir / "worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocalMemoriaError("local_memoria_writer_busy") from exc
        checkpoint_path = local_dir / CHECKPOINT_NAME
        checkpoint = _load_checkpoint(checkpoint_path)
        cursor = checkpoint["cursor"] if checkpoint else 0
        try:
            batch = preview_episode_batch(Path(ledger_path), Path(world_path), cursor=cursor, limit=limit)
        except EpisodeSyncContractError as exc:
            raise LocalMemoriaError(str(exc)) from exc
        if checkpoint:
            if checkpoint["world_id"] != batch["world_id"] or checkpoint["ledger_identity"] != batch["ledger_identity"]:
                raise LocalMemoriaError("local_source_identity_changed")
            if checkpoint["anchor_sha256"] != _anchor(Path(ledger_path), cursor):
                raise LocalMemoriaError("local_source_anchor_changed")
        namespace = "live:" + batch["world_id"]
        service = ProductEvidenceService.open(local_dir / "evidence", backend="sqlite", allow_fallback=False)
        existing: dict[str, Any] = {}
        for edge in service.core.evidence_history(namespace=namespace):
            duplicate = existing.get(edge.evidence_id)
            if duplicate is not None and duplicate != edge:
                raise LocalMemoriaError("conflicting_local_history")
            existing[edge.evidence_id] = edge
        if not checkpoint and (existing or service.receipt is not None):
            raise LocalMemoriaError("checkpoint_missing_for_existing_memory")
        if checkpoint:
            if len(existing) < checkpoint["edge_count"]:
                raise LocalMemoriaError("local_memory_regressed")
            if service.receipt is None:
                raise LocalMemoriaError("local_memoria_receipt_missing")
            # The snapshot may be ahead of the checkpoint if the process died
            # after durable save() but before atomic checkpoint publication.
            if len(existing) == checkpoint["edge_count"]:
                if service.receipt.as_dict() != checkpoint["memoria_receipt"]:
                    raise LocalMemoriaError("local_memory_receipt_mismatch")
        inserted = 0
        duplicates = 0
        for envelope in batch["episodes"]:
            for relation in _relations(envelope):
                old = existing.get(relation.evidence_id)
                if old is not None:
                    if not _edge_matches(old, relation):
                        raise LocalMemoriaError("conflicting_local_observation")
                    duplicates += 1
                    continue
                edge = service.core.observe_relation(
                    relation.subject, relation.predicate, relation.object,
                    evidence_id=relation.evidence_id, source_text=relation.source_text,
                    provenance=relation.provenance, origin=relation.origin,
                    namespace=relation.namespace, epoch=relation.epoch,
                )
                existing[relation.evidence_id] = edge
                inserted += 1
        if inserted:
            receipt = service.save().as_dict()
        else:
            receipt = service.receipt.as_dict() if service.receipt is not None else None
        next_cursor = batch["candidate_next_cursor"]
        if next_cursor != cursor:
            if receipt is None:
                raise LocalMemoriaError("local_memoria_receipt_missing")
            _durable_write_json(checkpoint_path, {
                "schema": LOCAL_SCHEMA,
                "world_id": batch["world_id"],
                "ledger_identity": batch["ledger_identity"],
                "cursor": next_cursor,
                "anchor_sha256": _anchor(Path(ledger_path), next_cursor),
                "edge_count": len(existing),
                "memoria_receipt": receipt,
                "last_record_key": batch["episodes"][-1]["record_key"] if batch["episodes"] else None,
            })
        return {
            "status": "ok",
            "mode": "local-memoria-rc2-observed-episodes",
            "backend": "sqlite",
            "world_id": batch["world_id"],
            "source_cursor": cursor,
            "durable_local_cursor": next_cursor if next_cursor != cursor else cursor,
            "observations_in_batch": len(batch["episodes"]),
            "new_relations": inserted,
            "duplicate_relations": duplicates,
            "total_relations": len(existing),
            "local_snapshot_persisted": receipt is not None,
            "central_transport_enabled": False,
            "world_mutated": False,
            "selection_authority": False,
        }
    finally:
        os.close(lock_fd)


def status(local_dir: Path) -> dict[str, Any]:
    cp = _load_checkpoint(Path(local_dir) / CHECKPOINT_NAME)
    return {
        "schema": LOCAL_SCHEMA,
        "initialized": cp is not None,
        "world_id": cp["world_id"] if cp else None,
        "durable_local_cursor": cp["cursor"] if cp else 0,
        "total_relations": cp["edge_count"] if cp else 0,
        "memoria_backend": cp["memoria_receipt"].get("backend") if cp else None,
        "central_transport_enabled": False,
        "world_write_authority": False,
    }
