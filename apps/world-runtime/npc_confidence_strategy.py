from __future__ import annotations

from copy import deepcopy
from typing import Any


class NpcConfidenceStrategy:
    """Decorate strategy ranking with non-authoritative decision confidence."""

    def __init__(self, base_strategy: Any, confidence_provider: Any) -> None:
        self.base_strategy = base_strategy
        self.confidence_provider = confidence_provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_strategy, name)

    def candidates(self, **kwargs: Any) -> list[dict[str, Any]]:
        fn = getattr(self.base_strategy, "candidates", None)
        if not callable(fn):
            return []
        return [deepcopy(row) for row in fn(**kwargs) if isinstance(row, dict)]

    def rank(self, candidates: list[dict[str, Any]], **kwargs: Any) -> list[dict[str, Any]]:
        fn = getattr(self.base_strategy, "rank", None)
        if not callable(fn):
            return []
        rows = fn(candidates, **kwargs)
        assessor = getattr(self.confidence_provider, "assess", None)
        result: list[dict[str, Any]] = []
        for raw in rows:
            row = deepcopy(raw)
            confidence = assessor(row) if callable(assessor) else None
            row["decision_confidence"] = deepcopy(confidence) if isinstance(confidence, dict) else None
            result.append(row)
        return result

    def choose(self, candidates: list[dict[str, Any]], **kwargs: Any) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
        ranked = self.rank(candidates, **kwargs)
        return (deepcopy(ranked[0]) if ranked else None), ranked
