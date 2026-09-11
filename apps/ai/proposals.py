from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any


class AIProposalStore:
    """Append-only store for AI Router proposals.

    Proposal records live outside the deterministic world log. Reading current()
    folds the history by proposal_id and returns only the latest state.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    rows.append(value)
        return rows

    def current(self) -> list[dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        for row in self.history():
            proposal_id = str(row.get("proposal_id") or "").strip()
            if not proposal_id:
                continue
            if proposal_id not in latest:
                order.append(proposal_id)
            latest[proposal_id] = row
        return [latest[proposal_id] for proposal_id in order]

    def get(self, proposal_id: str) -> dict[str, Any] | None:
        proposal_id = proposal_id.strip()
        return next((row for row in self.current() if row.get("proposal_id") == proposal_id), None)

    def create(
        self,
        *,
        action: str | None,
        confidence: float,
        reason: str,
        original_text: str,
        model: str,
        gateway_text: str | None,
        actionable: bool,
        source: str,
        actor_id: str,
        display_name: str | None,
        metadata: dict[str, Any] | None = None,
        context_digest: str | None = None,
        context_schema_version: str | None = None,
        context_world_version: int | None = None,
        context_world_sequence: int | None = None,
        context_world_state_hash: str | None = None,
        context_actor_key: str | None = None,
        context_bound_entity_id: str | None = None,
    ) -> dict[str, Any]:
        created_at = time.time()
        record = {
            "proposal_id": f"ai-{int(created_at * 1000)}-{uuid.uuid4().hex[:10]}",
            "status": "pending" if actionable and gateway_text else "non_actionable",
            "action": action,
            "confidence": max(0.0, min(1.0, float(confidence))),
            "reason": reason,
            "original_text": original_text,
            "model": model,
            "gateway_text": gateway_text,
            "actionable": bool(actionable and gateway_text),
            "source": source,
            "actor_id": actor_id,
            "display_name": display_name,
            "metadata": dict(metadata or {}),
            "context": {
                "digest": context_digest,
                "schema_version": context_schema_version,
                "world_version": context_world_version,
                "world_sequence": context_world_sequence,
                "world_state_hash": context_world_state_hash,
                "actor_key": context_actor_key,
                "bound_entity_id": context_bound_entity_id,
            },
            "created_at_unix": created_at,
        }
        self._append(record)
        return record

    def mark_committed(self, proposal_id: str, *, world_event_id: str | None = None) -> dict[str, Any]:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError("proposta não encontrada")
        if current.get("status") != "pending":
            raise ValueError("proposta não está pendente")
        record = {
            **current,
            "status": "committed",
            "committed_at_unix": time.time(),
            "world_event_id": world_event_id,
        }
        self._append(record)
        return record

    def mark_rejected(self, proposal_id: str, *, reason: str) -> dict[str, Any]:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError("proposta não encontrada")
        if current.get("status") != "pending":
            raise ValueError("proposta não está pendente")
        record = {
            **current,
            "status": "rejected",
            "rejected_at_unix": time.time(),
            "rejection_reason": reason[:500],
        }
        self._append(record)
        return record

    def mark_stale(
        self,
        proposal_id: str,
        *,
        current_world_version: int,
        current_world_sequence: int,
        current_world_state_hash: str | None,
    ) -> dict[str, Any]:
        current = self.get(proposal_id)
        if current is None:
            raise KeyError("proposta não encontrada")
        if current.get("status") != "pending":
            raise ValueError("proposta não está pendente")
        record = {
            **current,
            "status": "stale",
            "stale_at_unix": time.time(),
            "stale_world": {
                "version": int(current_world_version),
                "sequence": int(current_world_sequence),
                "state_hash": current_world_state_hash,
            },
        }
        self._append(record)
        return record

    def _append(self, record: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
