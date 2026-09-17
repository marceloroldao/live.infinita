from __future__ import annotations

from collections import defaultdict, deque
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
    """Aggregates audience telemetry and emits proposals only; never mutates World State.

    Events are retained only inside the largest active rule window for each event kind.
    This keeps memory and per-event work bounded during long or high-volume Lives.
    """

    def __init__(self, rules: tuple[AudienceRule, ...] = DEFAULT_RULES) -> None:
        self.rules = rules
        self._events_by_kind: dict[str, deque[float]] = defaultdict(deque)
        self._max_window_by_kind: dict[str, float] = {}
        for rule in rules:
            current = self._max_window_by_kind.get(rule.kind, 0.0)
            self._max_window_by_kind[rule.kind] = max(current, rule.window_seconds)
        self._last_trigger_bucket: dict[str, int] = {}

    def _prune(self, kind: str, now: float) -> None:
        events = self._events_by_kind[kind]
        max_window = self._max_window_by_kind.get(kind, 0.0)
        cutoff = now - max_window
        while events and events[0] < cutoff:
            events.popleft()

    def _count_since(self, kind: str, cutoff: float) -> int:
        events = self._events_by_kind[kind]
        # deque is ordered by ingestion time. Iterate from newest and stop at cutoff.
        count = 0
        for ts in reversed(events):
            if ts < cutoff:
                break
            count += 1
        return count

    def ingest(self, event: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
        ts = float(now if now is not None else event.get("received_at_unix", time()))
        kind = str(event.get("kind") or "")
        if not kind:
            return []

        events = self._events_by_kind[kind]
        # Normal sources are monotonic. If a late event arrives, insert in order so pruning remains correct.
        if events and ts < events[-1]:
            ordered = list(events)
            ordered.append(ts)
            ordered.sort()
            self._events_by_kind[kind] = deque(ordered)
        else:
            events.append(ts)
        self._prune(kind, ts)

        proposals: list[dict[str, Any]] = []
        for rule in self.rules:
            if kind != rule.kind:
                continue
            cutoff = ts - rule.window_seconds
            count = self._count_since(rule.kind, cutoff)
            trigger_bucket = count // rule.threshold
            previous_bucket = self._last_trigger_bucket.get(rule.rule_id, 0)

            # Buckets can fall when old events expire. Reset the baseline so a fresh threshold
            # crossing can trigger again instead of being suppressed forever.
            if trigger_bucket < previous_bucket:
                previous_bucket = trigger_bucket
                self._last_trigger_bucket[rule.rule_id] = trigger_bucket

            if trigger_bucket <= previous_bucket:
                continue
            self._last_trigger_bucket[rule.rule_id] = trigger_bucket
            proposals.append({
                "proposal_id": f"{rule.rule_id}-{int(ts * 1000)}-{trigger_bucket}",
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

    def retained_event_count(self) -> int:
        return sum(len(events) for events in self._events_by_kind.values())

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
