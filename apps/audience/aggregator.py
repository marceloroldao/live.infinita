from __future__ import annotations

from dataclasses import dataclass
from time import time
from typing import Any


@dataclass(frozen=True)
class AudienceRule:
    rule_id: str
    kind: str
    threshold: int
    window_seconds: float
    proposed_action: str
    text: str


DEFAULT_RULES = (
    AudienceRule("joins-10-30s", "join", 10, 30.0, "spawn_person", "+ visitante"),
    AudienceRule("likes-50-30s", "like", 50, 30.0, "toggle_fire", "fogueira"),
    AudienceRule("gift-any", "gift", 1, 30.0, "spawn_person", "+ visitante"),
)


class AudienceAggregator:
    """Aggregates audience telemetry and emits proposals only; never mutates World State."""

    def __init__(self, rules: tuple[AudienceRule, ...] = DEFAULT_RULES) -> None:
        self.rules = rules
        self._events: list[dict[str, Any]] = []
        self._last_trigger_count: dict[str, int] = {}

    def ingest(self, event: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
        ts = float(now if now is not None else event.get("received_at_unix", time()))
        enriched = dict(event)
        enriched["received_at_unix"] = ts
        self._events.append(enriched)

        proposals: list[dict[str, Any]] = []
        for rule in self.rules:
            if enriched.get("kind") != rule.kind:
                continue
            cutoff = ts - rule.window_seconds
            count = sum(
                1
                for item in self._events
                if item.get("kind") == rule.kind and float(item.get("received_at_unix", 0)) >= cutoff
            )
            previous_trigger = self._last_trigger_count.get(rule.rule_id, 0)
            trigger_number = count // rule.threshold
            if trigger_number <= previous_trigger:
                continue
            self._last_trigger_count[rule.rule_id] = trigger_number
            proposals.append({
                "proposal_id": f"{rule.rule_id}-{int(ts * 1000)}-{trigger_number}",
                "rule_id": rule.rule_id,
                "source": "audience-aggregator",
                "trigger_kind": rule.kind,
                "threshold": rule.threshold,
                "window_seconds": rule.window_seconds,
                "observed_count": count,
                "proposed_action": rule.proposed_action,
                "gateway_text": rule.text,
                "status": "pending",
                "created_at_unix": ts,
            })
        return proposals

    def rules_snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "rule_id": r.rule_id,
                "kind": r.kind,
                "threshold": r.threshold,
                "window_seconds": r.window_seconds,
                "proposed_action": r.proposed_action,
                "gateway_text": r.text,
            }
            for r in self.rules
        ]
