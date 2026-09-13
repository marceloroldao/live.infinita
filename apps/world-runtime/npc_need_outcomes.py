from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


class NpcNeedOutcomeProcessor:
    """Apply deterministic internal satisfaction after need-driven plans complete.

    This is not authoritative world replay. It updates the compact NPC need state
    exactly once per completed plan and writes an audit trail for observability.
    When a learning provider is present, the actually achieved reduction is also
    recorded against the selected target exactly once per outcome id, using the
    decision-time learning context captured in the semantic intent.
    """

    DEFAULT_SATISFACTION = {
        "safety": 0.50,
        "energy": 0.40,
        "social": 0.35,
        "curiosity": 0.30,
    }

    def __init__(
        self,
        path: Path,
        plan_ledger: Any,
        need_dynamics: Any,
        *,
        satisfaction: dict[str, float] | None = None,
        learning_provider: Any | None = None,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.plan_ledger = plan_ledger
        self.need_dynamics = need_dynamics
        self.learning_provider = learning_provider
        self.satisfaction = dict(self.DEFAULT_SATISFACTION)
        for key, value in dict(satisfaction or {}).items():
            if key in self.satisfaction:
                self.satisfaction[key] = max(0.0, float(value))

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        rows.append(value)
        return rows

    def _append(self, row: dict[str, Any]) -> dict[str, Any]:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        return row

    def _processed_ids(self) -> set[str]:
        return {str(row.get("plan_id")) for row in self.history() if row.get("plan_id")}

    def _learn(self, record: dict[str, Any], outcome: dict[str, Any], *, npc_id: str, need: str, plan_id: str) -> dict[str, Any] | None:
        if self.learning_provider is None:
            return None
        observer = getattr(self.learning_provider, "observe", None)
        if not callable(observer):
            return None
        intent = record.get("intent") if isinstance(record.get("intent"), dict) else {}
        target_id = str(intent.get("target_entity_id") or "").strip()
        if not target_id:
            return None
        before = float(outcome.get("before", 0.0))
        after = float(outcome.get("after", before))
        achieved = min(1.0, max(0.0, before - after))
        kwargs = {
            "outcome_id": str(outcome.get("outcome_id") or f"plan-completed:{plan_id}:{need}"),
            "npc_id": npc_id,
            "need": need,
            "target_entity_id": target_id,
            "satisfaction": achieved,
            "plan_id": plan_id,
            "proposal_id": str(record.get("proposal_id") or "").strip() or None,
        }
        context = intent.get("learning_context") if isinstance(intent.get("learning_context"), dict) else None
        try:
            return observer(**kwargs, context=deepcopy(context))
        except TypeError:
            # Backward-compatible adapter for v1 learning providers.
            return observer(**kwargs)

    def process_completed(self) -> list[dict[str, Any]]:
        processed = self._processed_ids()
        results: list[dict[str, Any]] = []
        for record in self.plan_ledger.current():
            plan_id = str(record.get("plan_id") or "").strip()
            if not plan_id or plan_id in processed or str(record.get("status") or "") != "completed":
                continue
            intent = record.get("intent") if isinstance(record.get("intent"), dict) else {}
            need = str(intent.get("need") or "").strip().lower()
            npc_id = str(record.get("actor_entity_id") or intent.get("actor_entity_id") or "").strip()
            if need not in self.satisfaction or not npc_id:
                continue

            outcome_id = f"plan-completed:{plan_id}:{need}"
            outcome = self.need_dynamics.satisfy(
                npc_id,
                need,
                self.satisfaction[need],
                outcome_id=outcome_id,
                metadata={
                    "plan_id": plan_id,
                    "proposal_id": record.get("proposal_id"),
                    "plan_revision": int(record.get("plan_revision", 0)),
                    "completed_steps": len(record.get("completed_steps") or []),
                    "target_entity_id": intent.get("target_entity_id"),
                    "learning_context": deepcopy(intent.get("learning_context")),
                },
            )
            learning = self._learn(record, outcome, npc_id=npc_id, need=need, plan_id=plan_id)
            row = {
                "need_outcome_schema": "npc_need_outcome_audit_v3",
                "plan_id": plan_id,
                "proposal_id": record.get("proposal_id"),
                "npc_id": npc_id,
                "need": need,
                "target_entity_id": intent.get("target_entity_id"),
                "learning_context": deepcopy(intent.get("learning_context")),
                "status": "applied",
                "outcome": deepcopy(outcome),
                "learning": deepcopy(learning),
            }
            self._append(row)
            processed.add(plan_id)
            results.append(row)
        return results
