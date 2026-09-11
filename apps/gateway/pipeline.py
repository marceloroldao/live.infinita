from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adapters import adapt_source
from envelope import UniversalEventEnvelope


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
    """Converte payloads de fontes distintas para UniversalEventEnvelope v1.0."""

    def normalize(self, payload: dict[str, Any]) -> UniversalEventEnvelope:
        source = str(payload.get("source", "simulator")).strip().lower()
        return adapt_source(source, payload)


class IntentEngine:
    """Interpretação determinística do MVP-004; LLM continua fora do caminho crítico."""

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

    def propose(self, event: UniversalEventEnvelope) -> ProposedAction:
        action = self.RULES.get(event.text.strip().lower())
        if action is None:
            return ProposedAction("unknown", 0.0, "nenhuma intenção determinística reconhecida")
        return ProposedAction(action, 1.0, "regra determinística MVP-004")


class RuleValidator:
    ALLOWED_SOURCES = {"simulator", "api", "tiktok", "youtube", "agent"}
    ALLOWED_ACTIONS = {"spawn_person", "move_tree", "toggle_fire", "set_night", "set_day", "reset"}

    def validate(self, event: UniversalEventEnvelope, proposed: ProposedAction) -> ValidationResult:
        if event.source not in self.ALLOWED_SOURCES:
            return ValidationResult(False, None, f"fonte não permitida: {event.source}")
        if proposed.action not in self.ALLOWED_ACTIONS:
            return ValidationResult(False, None, proposed.reason)
        if proposed.confidence < 1.0:
            return ValidationResult(False, None, "confiança insuficiente para commit determinístico")
        return ValidationResult(True, proposed.action, "ação aceita pelas regras do MVP-004")


class GatewayPipeline:
    def __init__(self) -> None:
        self.gateway = EventGateway()
        self.intent = IntentEngine()
        self.validator = RuleValidator()

    def process(self, payload: dict[str, Any]) -> tuple[UniversalEventEnvelope, ProposedAction, ValidationResult]:
        event = self.gateway.normalize(payload)
        proposed = self.intent.propose(event)
        validation = self.validator.validate(event, proposed)
        return event, proposed, validation
