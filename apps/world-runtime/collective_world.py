from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from packages.spatial import FileRegionColdStore


@dataclass(frozen=True)
class ThemeTemplate:
    biome: str
    arc: str
    title: str
    landmark_label: str
    narration: str


THEMES: dict[str, ThemeTemplate] = {
    "forest": ThemeTemplate(
        biome="forest",
        arc="mystery",
        title="O caminho entre as árvores",
        landmark_label="Árvore marcada pela audiência",
        narration="A vontade coletiva insiste na floresta. Um novo caminho se revela entre as árvores.",
    ),
    "river": ThemeTemplate(
        biome="river",
        arc="crossing",
        title="A margem que ainda não existia",
        landmark_label="Salgueiro da nova margem",
        narration="A audiência puxa a história em direção à água. Uma margem surge adiante e Nov ganha um novo destino.",
    ),
    "village": ThemeTemplate(
        biome="village",
        arc="encounter",
        title="Sinais de outras presenças",
        landmark_label="Fogueira da nova vila",
        narration="A intenção coletiva procura outras presenças. Luzes de uma pequena vila aparecem no horizonte.",
    ),
    "field": ThemeTemplate(
        biome="field",
        arc="horizon",
        title="O horizonte se abre",
        landmark_label="Árvore solitária do campo",
        narration="A audiência escolhe espaço e horizonte. A floresta se abre para uma nova campina.",
    ),
}

SLOTS: tuple[tuple[float, float], ...] = (
    (320.0, 145.0),
    (640.0, 145.0),
    (960.0, 145.0),
    (320.0, 575.0),
    (640.0, 575.0),
    (960.0, 575.0),
)

PREFERRED_SLOT_ORDER: dict[str, tuple[int, ...]] = {
    "forest": (3, 0, 4, 1, 5, 2),
    "river": (3, 4, 5, 0, 1, 2),
    "village": (2, 5, 1, 4, 0, 3),
    "field": (1, 0, 2, 4, 3, 5),
}


class CollectiveWorldEvolver:
    """Translate a converged collective signal into bounded canonical mutations."""

    def __init__(self, store: FileRegionColdStore, max_generated_regions: int = 6) -> None:
        self.store = store
        self.max_generated_regions = max(1, int(max_generated_regions))

    @staticmethod
    def _regions(world: dict[str, Any]) -> list[dict[str, Any]]:
        rows = world.get("regions")
        return [deepcopy(row) for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    @staticmethod
    def _region_by_id(regions: list[dict[str, Any]], region_id: str) -> dict[str, Any] | None:
        return next((row for row in regions if str(row.get("id") or "") == region_id), None)

    @staticmethod
    def _generated(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            row for row in regions
            if isinstance(row.get("metadata"), dict) and bool(row["metadata"].get("collective_generated"))
        ]

    @staticmethod
    def _distance_sq(a: tuple[float, float], b: tuple[float, float]) -> float:
        dx = a[0] - b[0]
        dy = a[1] - b[1]
        return dx * dx + dy * dy

    def _free_slot(self, regions: list[dict[str, Any]], theme: str) -> tuple[float, float] | None:
        occupied: list[tuple[float, float, float]] = []
        for row in regions:
            center = row.get("center") if isinstance(row.get("center"), dict) else {}
            try:
                occupied.append((float(center.get("x", 0.0)), float(center.get("y", 0.0)), float(row.get("radius", 120.0))))
            except (TypeError, ValueError):
                continue
        for index in PREFERRED_SLOT_ORDER.get(theme, tuple(range(len(SLOTS)))):
            candidate = SLOTS[index]
            if all(self._distance_sq(candidate, (x, y)) >= max(175.0, radius * 1.15) ** 2 for x, y, radius in occupied):
                return candidate
        return None

    def _anchor_region_id(self, regions: list[dict[str, Any]]) -> str:
        region_id = str(self.store.entity_region("nov") or "").strip()
        if region_id and self._region_by_id(regions, region_id) is not None:
            return region_id
        if self._region_by_id(regions, "clearing") is not None:
            return "clearing"
        return str(regions[0].get("id") or "") if regions else ""

    @staticmethod
    def _append_neighbor(region: dict[str, Any], neighbor_id: str) -> None:
        values = {str(value) for value in region.get("neighbors", []) if str(value)}
        values.add(neighbor_id)
        region["neighbors"] = sorted(values)

    def _existing_theme_target(self, regions: list[dict[str, Any]], theme: str) -> tuple[str | None, str | None]:
        template = THEMES[theme]
        candidates = [row for row in regions if str(row.get("biome") or "") == template.biome]
        candidates.sort(key=lambda row: (not bool((row.get("metadata") or {}).get("collective_generated")), str(row.get("id") or "")))
        for region in candidates:
            region_id = str(region.get("id") or "")
            for entity in self.store.load_region(region_id):
                if not isinstance(entity, dict) or str(entity.get("type") or "") == "human":
                    continue
                entity_id = str(entity.get("id") or "").strip()
                if entity_id:
                    return region_id, entity_id
        return None, None

    def plan(self, world: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
        theme = str(decision.get("dominant") or "").strip().lower()
        if theme not in THEMES:
            raise ValueError(f"unsupported collective theme: {theme}")
        template = THEMES[theme]
        chapter = max(1, int(decision.get("chapter", 1)))
        regions = self._regions(world)
        if not regions:
            raise ValueError("collective evolution requires world regions")
        anchor_id = self._anchor_region_id(regions)
        anchor = self._region_by_id(regions, anchor_id)
        if anchor is None:
            raise ValueError("collective evolution could not resolve anchor region")

        generated = self._generated(regions)
        slot = self._free_slot(regions, theme) if len(generated) < self.max_generated_regions else None
        operations: list[dict[str, Any]] = []
        created_region_id: str | None = None
        target_entity_id: str | None = None

        if slot is not None:
            created_region_id = f"collective_{theme}_{chapter:03d}"
            if self._region_by_id(regions, created_region_id) is not None:
                raise ValueError(f"collective region already exists: {created_region_id}")
            new_region = {
                "id": created_region_id,
                "center": {"x": slot[0], "y": slot[1]},
                "radius": 128 if theme == "village" else 145,
                "biome": template.biome,
                "neighbors": [anchor_id],
                "metadata": {
                    "label": template.title,
                    "collective_generated": True,
                    "collective_theme": theme,
                    "collective_chapter": chapter,
                },
            }
            self._append_neighbor(anchor, created_region_id)
            regions.append(new_region)
            regions.sort(key=lambda row: str(row.get("id") or ""))
            target_entity_id = f"collective_landmark_{chapter:03d}"
            entity_type = "campfire" if theme == "village" else "tree"
            properties: dict[str, Any] = {
                "label": template.landmark_label,
                "collective_generated": True,
                "collective_theme": theme,
                "risk_level": 0.04 if theme in {"field", "village"} else 0.12,
            }
            if entity_type == "campfire":
                properties["lit"] = True
            operations.extend([
                {"op": "set_world", "path": ["regions"], "value": regions},
                {
                    "op": "create",
                    "entity": {
                        "id": target_entity_id,
                        "type": entity_type,
                        "region_id": created_region_id,
                        "position": {"x": slot[0], "y": slot[1]},
                        "scale": 1.18 if entity_type == "tree" else 0.92,
                        "properties": properties,
                    },
                },
            ])
        else:
            created_region_id, target_entity_id = self._existing_theme_target(regions, theme)
            if target_entity_id is None:
                target_entity_id = "ancient_tree" if self.store.get_entity("ancient_tree") else "fire_01"
                created_region_id = self.store.entity_region(target_entity_id)

        if target_entity_id and self.store.get_entity("nov") is not None:
            operations.append({
                "op": "set",
                "entity_id": "nov",
                "path": ["properties", "curiosity_target_entity_id"],
                "value": target_entity_id,
            })
            operations.append({
                "op": "set",
                "entity_id": "nov",
                "path": ["properties", "needs", "curiosity"],
                "value": 0.92,
            })

        story = {
            "chapter": chapter,
            "arc": template.arc,
            "motif": theme,
            "title": template.title,
            "source": "collective_intent",
            "target_region_id": created_region_id,
            "target_entity_id": target_entity_id,
            "audience": {
                "score": decision.get("dominant_score"),
                "dominance": decision.get("dominance"),
                "contributors": decision.get("contributors"),
            },
            "updated_at_unix": decision.get("decided_at_unix"),
        }
        operations.extend([
            {"op": "set_world", "path": ["story"], "value": story},
            {
                "op": "set_world",
                "path": ["collective_intent"],
                "value": {
                    "dominant": theme,
                    "score": decision.get("dominant_score"),
                    "dominance": decision.get("dominance"),
                    "contributors": decision.get("contributors"),
                    "scores": deepcopy(decision.get("scores") or {}),
                    "chapter": chapter,
                    "applied": True,
                },
            },
        ])
        return {
            "operations": operations,
            "narration": template.narration,
            "theme": theme,
            "chapter": chapter,
            "region_id": created_region_id,
            "target_entity_id": target_entity_id,
            "story": story,
        }
