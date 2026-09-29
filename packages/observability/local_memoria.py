"""Offline local Memoria.ia RC2 EvidenceCore with incremental SQLite persistence.

The cognition/graph is the REAL pinned memoria_resolutiva.evidence_core.EvidenceCore.
Only storage is a Live-side per-observation SQLite adapter: RC2 ProductEvidenceService
writes a full content-addressed graph snapshot on every save, which is unsuitable
for a continuously growing 2-vCPU Live VM (16 episodes consumed 66 MiB).
No network, LLM, authoritative world writes or synthetic conversational episodes.
"""
from __future__ import annotations

from hashlib import sha256
import fcntl
import json
import os
from pathlib import Path
import sqlite3
from typing import Any

from packages.observability.nov_episode_sync import EpisodeSyncContractError, preview_episode_batch

LOCAL_SCHEMA = "live-infinita-local-memoria-checkpoint/v2"
LOCAL_PROVENANCE = "live.infinita:npc_episode_v1"
PINNED_MEMORIA_COMMIT = "e38f27b639bec1cfcb83694c1418a4d01f250ffd"
DB_NAME = "memoria-local.sqlite3"
MAX_STORED_ENVELOPE = 8192


class LocalMemoriaError(ValueError):
    """Do not acknowledge local progress when source or storage is ambiguous."""


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _anchor(ledger_path: Path, cursor: int) -> str:
    if cursor < 0:
        raise LocalMemoriaError("invalid_local_cursor")
    with Path(ledger_path).open("rb") as source:
        source.seek(0, os.SEEK_END)
        if cursor > source.tell():
            raise LocalMemoriaError("ledger_truncated_after_checkpoint")
        source.seek(max(0, cursor - 4096))
        return sha256(source.read(min(cursor, 4096))).hexdigest()


def _open_store(path: Path, *, readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    else:
        db = sqlite3.connect(path, timeout=5, isolation_level=None)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=FULL")
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
            CREATE TABLE IF NOT EXISTS observations (
                record_key TEXT PRIMARY KEY,
                content_sha256 TEXT NOT NULL,
                episode_id TEXT NOT NULL,
                logical_tick INTEGER NOT NULL,
                need TEXT,
                target_entity_id TEXT,
                payload TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_nov_observation_need_tick
                ON observations(need, logical_tick DESC);
            CREATE INDEX IF NOT EXISTS idx_nov_observation_target_tick
                ON observations(target_entity_id, logical_tick DESC);
            CREATE TABLE IF NOT EXISTS checkpoint (
                id INTEGER PRIMARY KEY CHECK(id = 1),
                payload TEXT NOT NULL
            );
        """)
    return db


def _load_checkpoint(db: sqlite3.Connection) -> dict[str, Any] | None:
    row = db.execute("SELECT payload FROM checkpoint WHERE id=1").fetchone()
    if row is None:
        return None
    try:
        if len(row[0]) > 8192:
            raise LocalMemoriaError("oversized_local_checkpoint")
        value = json.loads(row[0])
    except (ValueError, TypeError) as exc:
        if isinstance(exc, LocalMemoriaError):
            raise
        raise LocalMemoriaError("invalid_local_checkpoint") from exc
    if not isinstance(value, dict) or value.get("schema") != LOCAL_SCHEMA:
        raise LocalMemoriaError("invalid_local_checkpoint")
    for field in ("world_id", "ledger_identity", "cursor", "anchor_sha256", "observation_count"):
        if field not in value:
            raise LocalMemoriaError("incomplete_local_checkpoint")
    if (isinstance(value["cursor"], bool) or not isinstance(value["cursor"], int) or value["cursor"] < 0
            or isinstance(value["observation_count"], bool) or not isinstance(value["observation_count"], int)
            or value["observation_count"] < 0):
        raise LocalMemoriaError("invalid_local_checkpoint")
    return value


def _validate_observation(entry: dict[str, Any]) -> None:
    from packages.observability.nov_episode_sync import SCHEMA
    if entry.get("schema") != SCHEMA or entry.get("authority") != "observed-outcome-only" or entry.get("world_write_authority") is not False:
        raise LocalMemoriaError("invalid_stored_observation_schema")
    source = entry.get("source")
    if not isinstance(source, dict) or source.get("system") != "live.infinita" or source.get("entity_id") != "nov":
        raise LocalMemoriaError("invalid_stored_observation_source")
    if source.get("episode_id") != "plan:" + str(source.get("plan_id", "")):
        raise LocalMemoriaError("invalid_stored_observation_plan")
    identity = {k: source.get(k) for k in ("system", "world_id", "entity_id", "episode_id")}
    if sha256(_canonical(identity).encode("utf-8")).hexdigest() != entry.get("record_key"):
        raise LocalMemoriaError("local_observation_key_mismatch")
    unsigned = {key: val for key, val in entry.items() if key != "content_sha256"}
    if sha256(_canonical(unsigned).encode("utf-8")).hexdigest() != entry.get("content_sha256"):
        raise LocalMemoriaError("local_observation_digest_mismatch")


def _relations(envelope: dict[str, Any]) -> tuple[tuple[str, str, str, str], ...]:
    src = envelope["source"]
    obs = envelope["observation"]
    key = envelope["record_key"]
    namespace = "live:" + src["world_id"]
    episode = "live:episode:live-obs:" + key[:40]
    links = [("observed_experience", "live:entity:" + src["world_id"] + ":nov", "experience")]
    if obs["target_entity_id"] is not None:
        links.append(("experienced_target", "live:entity:" + src["world_id"] + ":" + obs["target_entity_id"], "target"))
    if obs["need"] is not None:
        links.append(("experienced_need", "live:need:" + src["world_id"] + ":" + obs["need"], "need"))
    if obs["strategy_id"] is not None:
        links.append(("experienced_strategy", "live:strategy:" + src["world_id"] + ":" + obs["strategy_id"], "strategy"))
    return tuple((episode, predicate, obj, "live-obs:" + key[:40] + ":" + suffix)
                 for predicate, obj, suffix in links)


def _observe_in_core(core: Any, envelope: dict[str, Any]) -> int:
    src = envelope["source"]
    origin = "live.infinita:" + src["world_id"]
    namespace = "live:" + src["world_id"]
    # This is structured source serialization, never a made-up utterance.
    source_payload = _canonical({key: val for key, val in envelope.items() if key != "content_sha256"})
    edges = _relations(envelope)
    for subject, predicate, obj, evidence_id in edges:
        core.observe_relation(
            subject, predicate, obj,
            evidence_id=evidence_id,
            source_text=source_payload,
            provenance=LOCAL_PROVENANCE,
            origin=origin,
            namespace=namespace,
            epoch=envelope["observation"]["logical_tick"],
        )
    return len(edges)


def load_real_evidence_core(db: sqlite3.Connection):
    """Cold-rebuild genuine Memoria.ia RC2 graph, preserving source and epoch."""
    from memoria_resolutiva.evidence_core import EvidenceCore
    core = EvidenceCore()
    previous: set[str] = set()
    total_relations = 0
    for key, digest, payload in db.execute(
        "SELECT record_key, content_sha256, payload FROM observations ORDER BY logical_tick, record_key"
    ):
        if len(payload) > MAX_STORED_ENVELOPE:
            raise LocalMemoriaError("oversized_stored_observation")
        try:
            entry = json.loads(payload)
            _validate_observation(entry)
        except (ValueError, TypeError, KeyError) as exc:
            raise LocalMemoriaError("corrupt_local_observation") from exc
        if entry["record_key"] != key or entry["content_sha256"] != digest or key in previous:
            raise LocalMemoriaError("corrupt_local_observation_index")
        previous.add(key)
        total_relations += _observe_in_core(core, entry)
    return core, total_relations


def sync_once(ledger_path: Path, world_path: Path, local_dir: Path, *, limit: int = 8) -> dict[str, Any]:
    """One bounded batch, observations + local cursor committed atomically."""
    local_dir = Path(local_dir)
    local_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_fd = os.open(local_dir / "worker.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LocalMemoriaError("local_memoria_writer_busy") from exc
        with _open_store(local_dir / DB_NAME) as db:
            checkpoint = _load_checkpoint(db)
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
            count = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
            if not checkpoint and count:
                raise LocalMemoriaError("checkpoint_missing_for_existing_memory")
            if checkpoint and count != checkpoint["observation_count"]:
                raise LocalMemoriaError("local_memory_checkpoint_count_mismatch")
            core, total_relations = load_real_evidence_core(db)
            existing = {
                key: (digest, payload)
                for key, digest, payload in db.execute("SELECT record_key, content_sha256, payload FROM observations")
            }
            to_insert = []
            duplicates = 0
            new_relations = 0
            for envelope in batch["episodes"]:
                _validate_observation(envelope)
                key = envelope["record_key"]
                digest = envelope["content_sha256"]
                encoded = _canonical(envelope)
                if len(encoded) > MAX_STORED_ENVELOPE:
                    raise LocalMemoriaError("oversized_local_observation")
                if key in existing:
                    if existing[key] != (digest, encoded):
                        raise LocalMemoriaError("conflicting_local_observation")
                    duplicates += 1
                    continue
                new_relations += _observe_in_core(core, envelope)
                to_insert.append((
                    key, digest, envelope["source"]["episode_id"],
                    envelope["observation"]["logical_tick"],
                    envelope["observation"]["need"],
                    envelope["observation"]["target_entity_id"], encoded,
                ))
                existing[key] = (digest, encoded)
            next_cursor = batch["candidate_next_cursor"]
            if next_cursor != cursor:
                marker = {
                    "schema": LOCAL_SCHEMA,
                    "world_id": batch["world_id"],
                    "ledger_identity": batch["ledger_identity"],
                    "cursor": next_cursor,
                    "anchor_sha256": _anchor(Path(ledger_path), next_cursor),
                    "observation_count": count + len(to_insert),
                    "last_record_key": batch["episodes"][-1]["record_key"] if batch["episodes"] else None,
                }
                db.execute("BEGIN IMMEDIATE")
                try:
                    db.executemany("""
                        INSERT INTO observations (
                            record_key, content_sha256, episode_id, logical_tick, need,
                            target_entity_id, payload
                        ) VALUES (?,?,?,?,?,?,?)
                    """, to_insert)
                    db.execute(
                        "INSERT INTO checkpoint(id,payload) VALUES(1,?) "
                        "ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                        (_canonical(marker),),
                    )
                    db.commit()
                except Exception:
                    db.rollback()
                    raise
            return {
                "status": "ok",
                "mode": "real-memoria-rc2-core-local-sqlite",
                "backend": "sqlite-incremental",
                "world_id": batch["world_id"],
                "source_cursor": cursor,
                "durable_local_cursor": next_cursor,
                "observations_in_batch": len(batch["episodes"]),
                "new_observations": len(to_insert),
                "duplicate_observations": duplicates,
                "new_relations": new_relations,
                "total_observations": count + len(to_insert),
                "total_relations": total_relations + new_relations,
                "local_sqlite_transaction_committed": next_cursor == cursor or db.in_transaction is False,
                "central_transport_enabled": False,
                "world_mutated": False,
                "selection_authority": False,
            }
    finally:
        os.close(lock_fd)


def status(local_dir: Path) -> dict[str, Any]:
    path = Path(local_dir) / DB_NAME
    if not path.is_file():
        return {
            "schema": LOCAL_SCHEMA, "initialized": False, "world_id": None,
            "durable_local_cursor": 0, "total_observations": 0,
            "memoria_backend": "sqlite-incremental", "central_transport_enabled": False,
            "world_write_authority": False,
        }
    with _open_store(path, readonly=True) as db:
        cp = _load_checkpoint(db)
        count = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
    if not cp and count:
        raise LocalMemoriaError("checkpoint_missing_for_existing_memory")
    if cp and count != cp["observation_count"]:
        raise LocalMemoriaError("local_memory_checkpoint_count_mismatch")
    return {
        "schema": LOCAL_SCHEMA,
        "initialized": cp is not None,
        "world_id": cp["world_id"] if cp else None,
        "durable_local_cursor": cp["cursor"] if cp else 0,
        "total_observations": count,
        "memoria_backend": "sqlite-incremental",
        "central_transport_enabled": False,
        "world_write_authority": False,
    }
