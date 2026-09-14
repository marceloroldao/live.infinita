from __future__ import annotations

from dataclasses import dataclass
from math import hypot
from typing import Any


@dataclass(frozen=True)
class InterestConfig:
    # 280 keeps nearby scenic anchors (for example the clearing campfire) hot
    # while Nov is at the shelter, without materializing the whole warm set.
    hot_radius: float = 280.0
    warm_radius: float = 420.0
    forward_bias: float = 0.35
    semantic_boost: float = 0.45
    max_hot_entities: int = 96
    max_warm_entities: int = 192

    def validate(self) -> None:
        if self.hot_radius <= 0:
            raise ValueError("hot_radius must be positive")
        if self.warm_radius < self.hot_radius:
            raise ValueError("warm_radius must be >= hot_radius")
        if not 0.0 <= self.forward_bias <= 1.0:
            raise ValueError("forward_bias must be between 0 and 1")
        if not 0.0 <= self.semantic_boost <= 1.0:
            raise ValueError("semantic_boost must be between 0 and 1")
        if self.max_hot_entities < 1 or self.max_warm_entities < 1:
            raise ValueError("entity caps must be positive")


class SpatialResolver:
    """Resolve the local interest slice without mutating global world state.

    Input data stays presentation-agnostic. The resolver only returns identifiers
    and small metadata required for hot/warm materialization.
    """

    def __init__(self, config: InterestConfig | None = None) -> None:
        self.config = config or InterestConfig()
        self.config.validate()

    @staticmethod
    def _xy(value: dict[str, Any]) -> tuple[float, float]:
        return float(value.get("x", 0.0)), float(value.get("y", 0.0))

    @staticmethod
    def _normalize_direction(direction: dict[str, Any] | None) -> tuple[float, float]:
        if not direction:
            return 0.0, 0.0
        x, y = float(direction.get("x", 0.0)), float(direction.get("y", 0.0))
        mag = hypot(x, y)
        if mag <= 1e-9:
            return 0.0, 0.0
        return x / mag, y / mag

    def _score_entity(
        self,
        observer: tuple[float, float],
        direction: tuple[float, float],
        entity: dict[str, Any],
    ) -> tuple[float, float]:
        ex, ey = self._xy(dict(entity.get("position", {})))
        dx, dy = ex - observer[0], ey - observer[1]
        distance = hypot(dx, dy)
        if distance <= 1e-9:
            forward = 1.0
        else:
            forward = max(0.0, (dx / distance) * direction[0] + (dy / distance) * direction[1])

        properties = entity.get("properties", {})
        semantic = 0.0
        if isinstance(properties, dict):
            semantic = float(properties.get("importance", properties.get("salience", 0.0)) or 0.0)
        semantic = max(0.0, min(1.0, semantic))

        normalized_distance = min(1.0, distance / self.config.warm_radius)
        score = (
            1.0 - normalized_distance
            + forward * self.config.forward_bias
            + semantic * self.config.semantic_boost
        )
        return score, distance

    def resolve(
        self,
        *,
        observer: dict[str, Any],
        entities: list[dict[str, Any]],
        regions: list[dict[str, Any]] | None = None,
        direction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        origin = self._xy(dict(observer.get("position", observer)))
        heading = self._normalize_direction(direction)

        scored: list[tuple[float, float, str, dict[str, Any]]] = []
        for entity in entities:
            entity_id = str(entity.get("id", "")).strip()
            if not entity_id:
                continue
            score, distance = self._score_entity(origin, heading, entity)
            if distance <= self.config.warm_radius:
                scored.append((score, distance, entity_id, entity))

        scored.sort(key=lambda item: (-item[0], item[1], item[2]))

        hot: list[str] = []
        warm: list[str] = []
        for _score, distance, entity_id, _entity in scored:
            if distance <= self.config.hot_radius and len(hot) < self.config.max_hot_entities:
                hot.append(entity_id)
            elif len(warm) < self.config.max_warm_entities:
                warm.append(entity_id)

        region_hot: list[str] = []
        region_warm: list[str] = []
        for region in regions or []:
            region_id = str(region.get("id", "")).strip()
            if not region_id:
                continue
            center = region.get("center", {})
            rx, ry = self._xy(center if isinstance(center, dict) else {})
            distance = hypot(rx - origin[0], ry - origin[1])
            radius = float(region.get("radius", 0.0) or 0.0)
            if distance <= radius + self.config.hot_radius:
                region_hot.append(region_id)
            elif distance <= radius + self.config.warm_radius:
                region_warm.append(region_id)

        return {
            "observer": {"x": origin[0], "y": origin[1]},
            "hot": {"entity_ids": hot, "region_ids": sorted(region_hot)},
            "warm": {"entity_ids": warm, "region_ids": sorted(region_warm)},
            "cold_omitted": True,
            "policy": {
                "hot_radius": self.config.hot_radius,
                "warm_radius": self.config.warm_radius,
                "max_hot_entities": self.config.max_hot_entities,
                "max_warm_entities": self.config.max_warm_entities,
            },
        }
