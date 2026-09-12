from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable


@dataclass(frozen=True)
class MutationPrincipal:
    source: str
    actor_id: str
    authority: str
    subject_entity_id: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MutationPrincipal":
        source = str(value.get("source") or "").strip().lower()
        actor_id = str(value.get("actor_id") or "").strip()
        authority = str(value.get("authority") or "").strip().lower()
        subject = str(value.get("subject_entity_id") or "").strip() or None
        if not source:
            raise ValueError("principal.source is required")
        if not actor_id:
            raise ValueError("principal.actor_id is required")
        if not authority:
            raise ValueError("principal.authority is required")
        return cls(source=source, actor_id=actor_id, authority=authority, subject_entity_id=subject)


@dataclass(frozen=True)
class MutationDecision:
    accepted: bool
    reason: str
    principal: MutationPrincipal
    operations: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "accepted": self.accepted,
            "reason": self.reason,
            "principal": {
                "source": self.principal.source,
                "actor_id": self.principal.actor_id,
                "authority": self.principal.authority,
                "subject_entity_id": self.principal.subject_entity_id,
            },
            "operations": [deepcopy(op) for op in self.operations],
        }


class MutationGate:
    """Deterministic authorization gate for canonical world mutations.

    Authorities:
      system/operator: full access to canonical operations.
      world_agent: create/set/move/link/unlink; no remove or set_world.
      entity_agent: set/move/link/unlink only on subject_entity_id.
      audience/observer/unknown: no direct mutation authority.

    The gate never mutates storage. It only validates and decides.
    """

    ALL_OPS = frozenset({"create", "set", "move", "remove", "link", "unlink", "set_world"})
    WORLD_AGENT_OPS = frozenset({"create", "set", "move", "link", "unlink"})
    ENTITY_AGENT_OPS = frozenset({"set", "move", "link", "unlink"})

    @staticmethod
    def _canonical_op(operation: dict[str, Any]) -> str:
        if not isinstance(operation, dict):
            raise ValueError("operation must be an object")
        op = str(operation.get("op") or "").strip().lower()
        if not op:
            raise ValueError("operation.op is required")
        return op

    @staticmethod
    def _target_entity_id(operation: dict[str, Any]) -> str | None:
        op = str(operation.get("op") or "").strip().lower()
        if op == "create":
            entity = operation.get("entity")
            if isinstance(entity, dict):
                return str(entity.get("id") or "").strip() or None
            return None
        if op in {"set", "move", "remove", "link", "unlink"}:
            return str(operation.get("entity_id") or "").strip() or None
        return None

    def decide(
        self,
        operations: Iterable[dict[str, Any]],
        principal: MutationPrincipal | dict[str, Any],
    ) -> MutationDecision:
        if isinstance(principal, dict):
            principal = MutationPrincipal.from_dict(principal)
        if not isinstance(principal, MutationPrincipal):
            raise ValueError("principal is required")

        rows = tuple(deepcopy(list(operations)))
        if not rows:
            return MutationDecision(False, "no operations", principal, rows)

        authority = principal.authority
        if authority in {"system", "operator"}:
            allowed = self.ALL_OPS
        elif authority == "world_agent":
            allowed = self.WORLD_AGENT_OPS
        elif authority == "entity_agent":
            allowed = self.ENTITY_AGENT_OPS
            if not principal.subject_entity_id:
                return MutationDecision(False, "entity_agent requires subject_entity_id", principal, rows)
        else:
            return MutationDecision(False, f"authority has no direct mutation rights: {authority}", principal, rows)

        for index, operation in enumerate(rows):
            try:
                op = self._canonical_op(operation)
            except ValueError as exc:
                return MutationDecision(False, f"operation {index}: {exc}", principal, rows)
            if op not in self.ALL_OPS:
                return MutationDecision(False, f"operation {index}: unsupported operation: {op}", principal, rows)
            if op not in allowed:
                return MutationDecision(False, f"operation {index}: {authority} cannot perform {op}", principal, rows)
            if authority == "entity_agent":
                target = self._target_entity_id(operation)
                if target != principal.subject_entity_id:
                    return MutationDecision(
                        False,
                        f"operation {index}: entity_agent cannot mutate another entity",
                        principal,
                        rows,
                    )

        return MutationDecision(True, "accepted", principal, rows)
