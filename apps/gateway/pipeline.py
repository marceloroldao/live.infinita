from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NormalizedEvent:
    source: str
    actor_id: str
    kind: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ProposedAction:
    action: str
    confidence: float
    reason: str


@dataclass(frozen=True)
class ValidationResult:
    accepted: bool
    action: str | None
    reason: str


class EventGateway:
    """Normaliza qualquer fonte externa para um contrato único."""

    def normalize(self, payload: dict[str, Any]) -> NormalizedEvent:
        source = str(payload.get("source", "simulator")).strip().lower()
        actor_id = str(payload.get("actor_id", "local-user")).strip()
        kind = str(payload.get("kind", "text")).strip().lower()
        text = str(payload.get("text", "")).strip()
        if not text:
            raise ValueError("evento sem conteúdo")
        return NormalizedEvent(source, actor_id, kind, text, dict(payload.get("metadata") or {}))


class IntentEngine:
    """MVP-003: interpretação determinística; LLM poderá ser plugada depois."""

    RULES = {
        "+ visitante": "spawn_person",
        "adicionar visitante": "spawn_person",
        "spawn person": "spawn_person",
        "mover árvore": "move_tree",
        "mover arvore": "move_tree",
        "move tree": "move_tree",
        "fogueira": "toggle_fire",
        "alternar fogueira": "toggle_fire",
        "toggle fire": "toggle_fire",
        "noite": "set_night",
        "night": "set_night",
        "dia": "set_day",
        "day": "set_day",
        "reset": "reset",
    }

    def propose(self, event: NormalizedEvent) -> ProposedAction:
        text = event.text.strip().lower()
        action = self.RULES.get(text)
        if action is None:
            return ProposedAction("unknown", 0.0, "nenhuma intenção determinística reconhecida")
        return ProposedAction(action, 1.0, "regra determinística MVP-003")


class RuleValidator:
    ALLOWED_SOURCES = {"simulator", "api", "tiktok", "youtube", "agent"}
    ALLOWED_ACTIONS = {"spawn_person", "move_tree", "toggle_fire", "set_night", "set_day", "reset"}

    def validate(self, event: NormalizedEvent, proposed: ProposedAction) -> ValidationResult:
        if event.source not in self.ALLOWED_SOURCES:
            return ValidationResult(False, None, f"fonte não permitida: {event.source}")
        if proposed.action not in self.ALLOWED_ACTIONS:
            return ValidationResult(False, None, proposed.reason)
        if proposed.confidence < 1.0:
            return ValidationResult(False, None, "confiança insuficiente para commit determinístico")
        return ValidationResult(True, proposed.action, "ação aceita pelas regras do MVP-003")


class GatewayPipeline:
    def __init__(self) -> None:
        self.gateway = EventGateway()
        self.intent = IntentEngine()
        self.validator = RuleValidator()

    def process(self, payload: dict[str, Any]) -> tuple[NormalizedEvent, ProposedAction, ValidationResult]:
        event = self.gateway.normalize(payload)
        proposed = self.intent.propose(event)
        validation = self.validator.validate(event, proposed)
        return event, proposed, validation
