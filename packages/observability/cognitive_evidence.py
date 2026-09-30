from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from threading import RLock
from typing import Any

SCHEMA = "live-infinita-cognitive-evidence/v1"
AUDIENCE_HIERARCHY_SUFFIX = "audience-observed"
NARRATOR_HIERARCHY_SUFFIX = "narrator-generated"
ALLOWED_KINDS = frozenset({"audience_comment", "narrator_output"})
_RECORD_KEY = re.compile(r"^[0-9a-f]{64}$")


class CognitiveEvidenceError(ValueError):
    pass


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _text(value: Any, *, maximum: int = 20_000) -> str:
    clean = str(value or "").strip()
    if not clean:
        raise CognitiveEvidenceError("text is required")
    if len(clean) > maximum:
        raise CognitiveEvidenceError("text exceeds limit")
    return clean


def _world_id(world: dict[str, Any]) -> str:
    value = str(world.get("world_id") or "").strip()
    if not value or len(value) > 160 or not all(
        c.isascii() and (c.isalnum() or c in "._:-") for c in value
    ):
        raise CognitiveEvidenceError("invalid world identity")
    return value


def _world_snapshot(world: dict[str, Any]) -> dict[str, Any]:
    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    sequence = world.get("sequence", 0)
    if isinstance(sequence, bool):
        sequence = 0
    try:
        sequence = int(sequence)
    except (TypeError, ValueError):
        sequence = 0
    logical_tick = world.get("current_tick")
    if isinstance(logical_tick, bool):
        logical_tick = None
    try:
        logical_tick = None if logical_tick is None else int(logical_tick)
    except (TypeError, ValueError):
        logical_tick = None
    return {
        "world_sequence": max(0, sequence),
        "logical_tick": logical_tick if logical_tick is None or logical_tick >= 0 else None,
        "region_id": str(environment.get("region_id") or "").strip() or None,
        "biome": str(environment.get("biome") or "").strip() or None,
        "period": str(environment.get("period") or "").strip() or None,
        "weather": str(environment.get("weather") or "").strip() or None,
    }


def _record(
    *,
    world: dict[str, Any],
    kind: str,
    source_name: str,
    source_event_id: str,
    text: str,
    actor_id: str | None,
    display_name: str | None,
    generated_by: str | None = None,
    causal_parent_record_keys: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    kind = str(kind or "").strip()
    if kind not in ALLOWED_KINDS:
        raise CognitiveEvidenceError("unsupported evidence kind")
    world_id = _world_id(world)
    source_name = str(source_name or "").strip().lower()
    event_id = str(source_event_id or "").strip()
    if not source_name or len(source_name) > 96:
        raise CognitiveEvidenceError("invalid source name")
    if not event_id or len(event_id) > 512:
        raise CognitiveEvidenceError("invalid source event id")

    parents: list[str] = []
    for raw in causal_parent_record_keys:
        key = str(raw or "").strip().lower()
        if not _RECORD_KEY.fullmatch(key):
            raise CognitiveEvidenceError("invalid causal parent record key")
        if key not in parents:
            parents.append(key)

    identity = {
        "system": "live.infinita",
        "world_id": world_id,
        "kind": kind,
        "source": source_name,
        "source_event_id": event_id,
    }
    record_key = sha256(_canonical_bytes(identity)).hexdigest()
    structural_sequence = int(record_key[:15], 16)
    hierarchy_suffix = (
        AUDIENCE_HIERARCHY_SUFFIX
        if kind == "audience_comment"
        else NARRATOR_HIERARCHY_SUFFIX
    )
    epistemic_class = (
        "external_expression"
        if kind == "audience_comment"
        else "generated_interpretation"
    )
    reinforcement_class = "observed" if kind == "audience_comment" else "generated"

    unsigned = {
        "schema": SCHEMA,
        "record_key": record_key,
        "source": {
            **identity,
            "actor_id": str(actor_id or "").strip() or None,
            "display_name": str(display_name or "").strip()[:80] or None,
            "generated_by": str(generated_by or "").strip()[:160] or None,
        },
        "observation": {
            **_world_snapshot(world),
            "text": _text(text),
        },
        "provenance": {
            "epistemic_class": epistemic_class,
            "causal_parent_record_keys": parents,
        },
        "memory_policy": {
            "hierarchy_id": f"live:{world_id}:{hierarchy_suffix}",
            "source_kind": kind,
            "structural_sequence": structural_sequence,
            "reinforcement_class": reinforcement_class,
            "can_reinforce_observed": kind == "audience_comment",
            "world_write_authority": False,
        },
    }
    return {
        **unsigned,
        "content_sha256": sha256(_canonical_bytes(unsigned)).hexdigest(),
    }


def audience_comment_evidence(
    world: dict[str, Any],
    comment: dict[str, Any],
) -> dict[str, Any]:
    return _record(
        world=world,
        kind="audience_comment",
        source_name=str(comment.get("source") or "audience"),
        source_event_id=str(comment.get("source_event_id") or ""),
        text=str(comment.get("text") or ""),
        actor_id=str(comment.get("actor_id") or "") or None,
        display_name=comment.get("display_name"),
    )


def narrator_output_evidence(
    world: dict[str, Any],
    cue: dict[str, Any],
    *,
    causal_parent_record_keys: tuple[str, ...] | list[str] = (),
) -> dict[str, Any]:
    return _record(
        world=world,
        kind="narrator_output",
        source_name="narrator",
        source_event_id=str(cue.get("cue_id") or ""),
        text=str(cue.get("text") or ""),
        actor_id="narrator",
        display_name="Narrador",
        generated_by=str(cue.get("generated_by") or "unknown"),
        causal_parent_record_keys=causal_parent_record_keys,
    )


def validate_evidence(record: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise CognitiveEvidenceError("unsupported cognitive evidence schema")
    key = str(record.get("record_key") or "").strip().lower()
    digest = str(record.get("content_sha256") or "").strip().lower()
    if not _RECORD_KEY.fullmatch(key) or not _RECORD_KEY.fullmatch(digest):
        raise CognitiveEvidenceError("invalid cognitive evidence digest")
    source = record.get("source")
    observation = record.get("observation")
    policy = record.get("memory_policy")
    provenance = record.get("provenance")
    if not all(isinstance(value, dict) for value in (source, observation, policy, provenance)):
        raise CognitiveEvidenceError("invalid cognitive evidence envelope")
    kind = str(source.get("kind") or "")
    if kind not in ALLOWED_KINDS or policy.get("source_kind") != kind:
        raise CognitiveEvidenceError("cognitive evidence kind mismatch")
    unsigned = {k: v for k, v in record.items() if k != "content_sha256"}
    expected = sha256(_canonical_bytes(unsigned)).hexdigest()
    if expected != digest:
        raise CognitiveEvidenceError("cognitive evidence content digest mismatch")
    return record


def to_structural_text_request(record: dict[str, Any]) -> dict[str, Any]:
    validate_evidence(record)
    source = record["source"]
    observation = record["observation"]
    policy = record["memory_policy"]
    speaker = str(source.get("display_name") or source.get("actor_id") or "anonymous").strip()
    raw = str(observation.get("text") or "").strip()
    kind = str(source.get("kind"))
    memory_text = (
        f"[viewer:{speaker}] {raw}"
        if kind == "audience_comment"
        else f"[narrator] {raw}"
    )
    return {
        "text": memory_text,
        "hierarchy_id": str(policy["hierarchy_id"]),
        "source_id": f"live:{kind}:{record['record_key'][:40]}",
        "sequence": int(policy["structural_sequence"]),
        "source_kind": kind,
    }


class CognitiveEvidenceLedger:
    """Append-only social evidence ledger with restart-safe identity checks."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._digests: dict[str, str] = {}
        self._last_record: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("rb") as fh:
            for line_number, raw in enumerate(fh, start=1):
                if not raw.endswith(b"\n"):
                    raise CognitiveEvidenceError(
                        f"torn cognitive evidence ledger at line {line_number}"
                    )
                try:
                    record = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise CognitiveEvidenceError(
                        f"invalid cognitive evidence ledger at line {line_number}"
                    ) from exc
                validate_evidence(record)
                key = record["record_key"]
                digest = record["content_sha256"]
                existing = self._digests.get(key)
                if existing is not None and existing != digest:
                    raise CognitiveEvidenceError("conflicting cognitive evidence identity")
                self._digests[key] = digest
                self._last_record = record

    @property
    def count(self) -> int:
        return len(self._digests)

    @property
    def last_record(self) -> dict[str, Any] | None:
        return None if self._last_record is None else dict(self._last_record)

    def append(self, record: dict[str, Any]) -> dict[str, Any]:
        validate_evidence(record)
        key = record["record_key"]
        digest = record["content_sha256"]
        with self._lock:
            existing = self._digests.get(key)
            if existing is not None:
                if existing != digest:
                    raise CognitiveEvidenceError("conflicting cognitive evidence identity")
                return {"stored": False, "record_key": key, "content_sha256": digest}
            payload = _canonical_bytes(record) + b"\n"
            fd = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                written = os.write(fd, payload)
                if written != len(payload):
                    raise CognitiveEvidenceError("short cognitive evidence append")
                os.fsync(fd)
            finally:
                os.close(fd)
            self._digests[key] = digest
            self._last_record = record
            return {"stored": True, "record_key": key, "content_sha256": digest}
