from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ActorObservation:
    source: str
    actor_id: str
    display_name: str | None
    kind: str
    source_event_id: str
    metadata: dict[str, Any]
    observed_at_unix: float

    @property
    def actor_key(self) -> str:
        return f"{self.source}:{self.actor_id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "actor_key": self.actor_key,
            "source": self.source,
            "actor_id": self.actor_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "source_event_id": self.source_event_id,
            "metadata": self.metadata,
            "observed_at_unix": self.observed_at_unix,
        }


class ActorStore:
    """Append-only actor observations with a folded current identity view.

    Cross-platform identities are intentionally not merged automatically.
    `tiktok:alice` and `youtube:alice` remain separate actor keys unless a future
    explicit identity-linking layer supplies evidence for a merge.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _append(self, row: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    def observe(
        self,
        *,
        source: str,
        actor_id: str,
        display_name: str | None,
        kind: str,
        source_event_id: str,
        metadata: dict[str, Any] | None = None,
        observed_at_unix: float | None = None,
    ) -> bool:
        source = source.strip().lower()
        actor_id = actor_id.strip()
        kind = kind.strip().lower()
        source_event_id = source_event_id.strip()
        if not source or not actor_id or not source_event_id:
            return False

        rows = self._read()
        duplicate = any(
            row.get("source") == source and row.get("source_event_id") == source_event_id
            for row in rows
        )
        if duplicate:
            return False

        observation = ActorObservation(
            source=source,
            actor_id=actor_id,
            display_name=display_name,
            kind=kind,
            source_event_id=source_event_id,
            metadata=dict(metadata or {}),
            observed_at_unix=float(observed_at_unix if observed_at_unix is not None else time.time()),
        )
        self._append(observation.to_dict())
        return True

    def observations(self) -> list[dict[str, Any]]:
        return self._read()

    def actors(self) -> list[dict[str, Any]]:
        states: dict[str, dict[str, Any]] = {}
        order: list[str] = []
        # Backfill and delayed delivery can append older observations last.
        # Stable sorting also makes equal timestamps follow append order.
        for row in sorted(self._read(), key=lambda row: row["observed_at_unix"]):
            actor_key = str(row.get("actor_key") or f"{row.get('source')}:{row.get('actor_id')}")
            if actor_key not in states:
                order.append(actor_key)
                states[actor_key] = {
                    "actor_key": actor_key,
                    "source": row.get("source"),
                    "actor_id": row.get("actor_id"),
                    "display_name": row.get("display_name"),
                    "display_names_seen": [],
                    "first_seen_unix": row.get("observed_at_unix"),
                    "last_seen_unix": row.get("observed_at_unix"),
                    "interactions_total": 0,
                    "interactions_by_kind": {},
                    "last_interaction": None,
                    "entity_id": None,
                }
            state = states[actor_key]
            name = row.get("display_name")
            if name and name not in state["display_names_seen"]:
                state["display_names_seen"].append(name)
            if name:
                state["display_name"] = name
            ts = row.get("observed_at_unix")
            state["last_seen_unix"] = ts
            state["interactions_total"] += 1
            kind = str(row.get("kind") or "unknown")
            state["interactions_by_kind"][kind] = state["interactions_by_kind"].get(kind, 0) + 1
            state["last_interaction"] = {
                "kind": kind,
                "source_event_id": row.get("source_event_id"),
                "observed_at_unix": ts,
            }
        return [states[key] for key in order]

    def get(self, source: str, actor_id: str) -> dict[str, Any] | None:
        actor_key = f"{source.strip().lower()}:{actor_id.strip()}"
        return next((actor for actor in self.actors() if actor.get("actor_key") == actor_key), None)
