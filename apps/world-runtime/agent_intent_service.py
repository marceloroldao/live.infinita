from __future__ import annotations

from copy import deepcopy
from typing import Any

from packages.spatial import AgentIntentResolver, MutationPrincipal


class AgentIntentService:
    """Resolve semantic intents, then submit canonical operations to the gate.

    This service deliberately does not bypass Proposal Ledger or Mutation Gate.
    Callers may use propose_only() for asynchronous/operator approval flows, or
    commit_resolved() when the principal is already authorized by policy.
    """

    def __init__(self, resolver: AgentIntentResolver, guarded_mutations: Any) -> None:
        self.resolver = resolver
        self.guarded_mutations = guarded_mutations

    def resolve(self, intent: dict[str, Any]) -> dict[str, Any]:
        return self.resolver.resolve(intent).as_dict()

    def propose_only(
        self,
        intent: dict[str, Any],
        *,
        principal: MutationPrincipal | dict[str, Any],
    ) -> dict[str, Any]:
        resolved = self.resolver.resolve(intent)
        decision = self.guarded_mutations.decide(
            [deepcopy(op) for op in resolved.operations],
            principal,
        )
        return {
            "intent": deepcopy(intent),
            "resolved_intent": resolved.as_dict(),
            "policy_preview": decision.as_dict(),
            "world_mutated": False,
        }

    def commit_resolved(
        self,
        intent: dict[str, Any],
        *,
        principal: MutationPrincipal | dict[str, Any],
        context: dict[str, Any] | None = None,
        narration: str = "",
    ) -> dict[str, Any]:
        resolved = self.resolver.resolve(intent)
        commit_context = deepcopy(context or {})
        commit_context["agent_intent"] = {
            "intent": deepcopy(intent),
            "resolved": resolved.as_dict(),
            "protocol": "agent_intent_v1",
        }
        result = self.guarded_mutations.commit(
            [deepcopy(op) for op in resolved.operations],
            principal=principal,
            context=commit_context,
            narration=narration,
        )
        return {
            **result,
            "resolved_intent": resolved.as_dict(),
        }
