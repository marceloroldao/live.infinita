from __future__ import annotations

from typing import Any

from envelope import EventActor, UniversalEventEnvelope, validate_envelope


class BaseAdapter:
    source: str

    def build(self, *, source_event_id: str, actor_id: str, text: str, display_name: str | None = None, metadata: dict[str, Any] | None = None) -> UniversalEventEnvelope:
        envelope = UniversalEventEnvelope(
            envelope_version="1.0",
            source=self.source,
            source_event_id=str(source_event_id),
            actor=EventActor(actor_id=str(actor_id), display_name=display_name),
            kind="text",
            text=str(text),
            metadata=dict(metadata or {}),
        )
        validate_envelope(envelope)
        return envelope


class SimulatorAdapter(BaseAdapter):
    source = "simulator"


class TikTokAdapter(BaseAdapter):
    source = "tiktok"


class YouTubeAdapter(BaseAdapter):
    source = "youtube"


class APIAdapter(BaseAdapter):
    source = "api"


class AgentAdapter(BaseAdapter):
    source = "agent"


ADAPTERS = {
    "simulator": SimulatorAdapter(),
    "tiktok": TikTokAdapter(),
    "youtube": YouTubeAdapter(),
    "api": APIAdapter(),
    "agent": AgentAdapter(),
}


def adapt_source(source: str, payload: dict[str, Any]) -> UniversalEventEnvelope:
    adapter = ADAPTERS.get(source.strip().lower())
    if adapter is None:
        raise ValueError(f"adaptador não suportado: {source}")
    return adapter.build(
        source_event_id=str(payload.get("source_event_id") or payload.get("event_id") or "local-1"),
        actor_id=str(payload.get("actor_id") or payload.get("user_id") or "anonymous"),
        display_name=payload.get("display_name") or payload.get("username"),
        text=str(payload.get("text") or payload.get("comment") or payload.get("message") or ""),
        metadata=dict(payload.get("metadata") or {}),
    )
