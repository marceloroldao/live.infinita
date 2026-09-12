from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spatial import MutationDecision, MutationGate, MutationPrincipal


class GuardedMutationService:
    """Policy boundary between untrusted mutation proposals and the world engine."""

    def __init__(self, engine: Any, gate: MutationGate | None = None) -> None:
        self.engine = engine
        self.gate = gate or MutationGate()

    def decide(
        self,
        operations: list[dict[str, Any]],
        principal: MutationPrincipal | dict[str, Any],
    ) -> MutationDecision:
        return self.gate.decide(operations, principal)

    def commit(
        self,
        operations: list[dict[str, Any]],
        *,
        principal: MutationPrincipal | dict[str, Any],
        context: dict[str, Any] | None = None,
        narration: str = "",
    ) -> dict[str, Any]:
        decision = self.decide(operations, principal)
        if not decision.accepted:
            return {
                "ok": False,
                "decision": decision.as_dict(),
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
        return {
            "ok": True,
            "decision": decision.as_dict(),
            "event": event,
            "delta": delta,
            "world": world,
        }
