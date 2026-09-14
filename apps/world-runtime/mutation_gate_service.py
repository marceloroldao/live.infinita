from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from mutation_decision_log import MutationDecisionLog
from packages.spatial import MutationDecision, MutationGate, MutationPrincipal


class GuardedMutationService:
    """Policy boundary between untrusted mutation proposals and the world engine."""

    def __init__(
        self,
        engine: Any,
        gate: MutationGate | None = None,
        decision_log_file: Path | None = None,
    ) -> None:
        self.engine = engine
        self.gate = gate or MutationGate()
        self.decision_log = MutationDecisionLog(decision_log_file) if decision_log_file else None

    def decide(
        self,
        operations: list[dict[str, Any]],
        principal: MutationPrincipal | dict[str, Any],
    ) -> MutationDecision:
        return self.gate.decide(operations, principal)

    def _state_hash(self) -> str:
        world = self.engine.load_world()
        return str(world.get("state_hash") or "")

    def _audit(
        self,
        *,
        decision: MutationDecision,
        before_state_hash: str,
        after_state_hash: str,
        context: dict[str, Any] | None,
        world_event_id: str | None,
    ) -> dict[str, Any] | None:
        if self.decision_log is None:
            return None
        return self.decision_log.append(
            decision=decision.as_dict(),
            before_state_hash=before_state_hash,
            after_state_hash=after_state_hash,
            context=context,
            world_event_id=world_event_id,
        )

    def commit(
        self,
        operations: list[dict[str, Any]],
        *,
        principal: MutationPrincipal | dict[str, Any],
        context: dict[str, Any] | None = None,
        narration: str = "",
    ) -> dict[str, Any]:
        before_state_hash = self._state_hash()
        decision = self.decide(operations, principal)
        if not decision.accepted:
            audit = self._audit(
                decision=decision,
                before_state_hash=before_state_hash,
                after_state_hash=before_state_hash,
                context=context,
                world_event_id=None,
            )
            return {
                "ok": False,
                "decision": decision.as_dict(),
                "audit": audit,
                "event": None,
                "delta": None,
                "world": None,
            }

        provenance = {
            "source": decision.principal.source,
            "actor_id": decision.principal.actor_id,
            "authority": decision.principal.authority,
            "subject_entity_id": decision.principal.subject_entity_id,
            "policy": "mutation_gate_v1",
            "decision": "accepted",
        }
        commit_context = deepcopy(context or {})
        commit_context["mutation_provenance"] = provenance
        event, delta, world = self.engine.commit_operations(
            [deepcopy(op) for op in decision.operations],
            source=decision.principal.source,
            context=commit_context,
            narration=narration,
        )
        after_state_hash = str(world.get("state_hash") or "")
        audit = self._audit(
            decision=decision,
            before_state_hash=before_state_hash,
            after_state_hash=after_state_hash,
            context=commit_context,
            world_event_id=str(event.get("event_id") or "") or None,
        )
        return {
            "ok": True,
            "decision": decision.as_dict(),
            "audit": audit,
            "event": event,
            "delta": delta,
            "world": world,
        }
