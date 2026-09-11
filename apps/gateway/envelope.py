from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class EventActor:
    actor_id: str
    display_name: str | None = None


@dataclass(frozen=True)
class UniversalEventEnvelope:
    envelope_version: str
    source: str
    source_event_id: str
    actor: EventActor
    kind: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class EnvelopeValidationError(ValueError):
    pass


def validate_envelope(envelope: UniversalEventEnvelope) -> None:
    if envelope.envelope_version != "1.0":
        raise EnvelopeValidationError("envelope_version não suportada")
    if not envelope.source.strip():
        raise EnvelopeValidationError("source ausente")
    if not envelope.source_event_id.strip():
        raise EnvelopeValidationError("source_event_id ausente")
    if not envelope.actor.actor_id.strip():
        raise EnvelopeValidationError("actor_id ausente")
    if envelope.kind != "text":
        raise EnvelopeValidationError(f"kind não suportado no MVP-004: {envelope.kind}")
    if not envelope.text.strip():
        raise EnvelopeValidationError("evento sem conteúdo")
