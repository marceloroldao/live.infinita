from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any


class MutationDecisionLog:
    """Append-only audit log for mutation policy decisions.

    This log is intentionally outside the authoritative world replay. Rejected
    proposals are auditable here without becoming world events or deltas.
    """

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _decision_id(record: dict[str, Any]) -> str:
        payload = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return "md_" + hashlib.sha256(payload).hexdigest()[:24]

    def append(
        self,
        *,
        decision: dict[str, Any],
        before_state_hash: str,
        after_state_hash: str,
        context: dict[str, Any] | None = None,
        world_event_id: str | None = None,
    ) -> dict[str, Any]:
        recorded_at = time.time()
        record = {
            "decision_schema": "mutation_decision_v1",
            "recorded_at_unix": recorded_at,
            "accepted": bool(decision.get("accepted")),
            "reason": str(decision.get("reason") or ""),
            "principal": dict(decision.get("principal") or {}),
            "operations": list(decision.get("operations") or []),
            "before_state_hash": str(before_state_hash or ""),
            "after_state_hash": str(after_state_hash or ""),
            "state_changed": str(before_state_hash or "") != str(after_state_hash or ""),
            "world_event_id": world_event_id,
            "context": dict(context or {}),
        }
        record["mutation_decision_id"] = self._decision_id(record)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return record

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows
