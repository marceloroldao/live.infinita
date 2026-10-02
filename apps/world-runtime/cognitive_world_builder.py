"""008C: bounded autonomous world-builder driven by cognitive terrain.

The Memoria.ia projection is only a stimulus. This agent independently derives
small canonical construction proposals from the current authoritative region
geometry, and every proposal must pass GuardedMutationService as a world_agent.

It never changes region topology, environment, existing entities, or removes
anything. Stable entity ids make retries/restarts idempotent.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import math
from pathlib import Path
import re
from typing import Any, Callable

from cognitive_terrain_projection import CognitiveTerrainError, CognitiveTerrainProjectionReader
from environmental_rules import EnvironmentalRulesError, derive_environmental_state, region_environment_map
from mutation_gate_service import GuardedMutationService
from packages.spatial import FileRegionColdStore, MutationPrincipal

TREE_BIOMES = frozenset({"forest", "clearing", "hills", "meadow"})
ROCK_BIOMES = frozenset({"forest", "clearing", "hills", "meadow", "moor", "highlands", "rocky"})
REST_BIOMES = frozenset({"forest", "clearing", "hills", "meadow", "moor"})
AGENT_ID = "cognitive-world-builder-v1"
MAX_CANDIDATES = 32
MAX_BUILDER_ENTITIES = 48
MAX_CREATIONS_PER_TICK = 1


@dataclass(frozen=True)
class BuildCandidate:
    entity_id: str
    entity_type: str
    region_id: str
    role: str
    slot: int
    cognitive_mass: float
    environmental_zone: str
    environmental_basis: str
    environmental_score: float
    priority: tuple[Any, ...]


class CognitiveWorldBuilderAgent:
    """Conservative single-writer world construction agent."""

    def __init__(
        self,
        store: FileRegionColdStore,
        guarded_mutations: GuardedMutationService,
        world_provider: Callable[[], dict[str, Any]],
        *,
        projection_file: Path,
        interval_ticks: int = 240,
        max_creations_per_tick: int = MAX_CREATIONS_PER_TICK,
    ) -> None:
        self.store = store
        self.guarded = guarded_mutations
        self.world_provider = world_provider
        self.reader = CognitiveTerrainProjectionReader(Path(projection_file))
        self.interval_ticks = max(8, int(interval_ticks))
        self.max_creations_per_tick = max(
            1, min(MAX_CREATIONS_PER_TICK, int(max_creations_per_tick))
        )
        self.principal = MutationPrincipal(
            source="cognitive_world_builder",
            actor_id="world-builder",
            authority="world_agent",
            subject_entity_id=None,
        )

    @staticmethod
    def _slug(value: str) -> str:
        value = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return value[:48] or "region"

    @staticmethod
    def _region_map(world: dict[str, Any]) -> dict[str, dict[str, Any]]:
        rows = world.get("regions")
        if not isinstance(rows, list):
            return {}
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            region_id = str(row.get("id") or "").strip()
            center = row.get("center")
            try:
                radius = float(row.get("radius", 0.0))
                x = float(center["x"]) if isinstance(center, dict) else 0.0
                y = float(center["y"]) if isinstance(center, dict) else 0.0
            except (KeyError, TypeError, ValueError):
                continue
            if region_id and radius > 0:
                result[region_id] = {
                    "id": region_id,
                    "center": {"x": x, "y": y},
                    "radius": radius,
                    "biome": str(row.get("biome") or "unknown"),
                }
        return result

    @classmethod
    def _stable_id(cls, region_id: str, entity_type: str, role: str, slot: int) -> str:
        return (
            f"builder_{cls._slug(region_id)}_{cls._slug(role)}_"
            f"{cls._slug(entity_type)}_{int(slot)}"
        )

    @classmethod
    def _candidate_specs(
        cls,
        projection: dict[str, Any],
        regions: dict[str, dict[str, Any]],
        environmental_regions: dict[str, dict[str, Any]],
    ) -> list[BuildCandidate]:
        result: list[BuildCandidate] = []
        rows = projection.get("regions")
        if not isinstance(rows, list):
            return result

        for raw in rows:
            if not isinstance(raw, dict):
                continue
            region_id = str(raw.get("region_id") or "").strip()
            region = regions.get(region_id)
            environment = environmental_regions.get(region_id)
            if region is None or environment is None:
                continue
            biome = str(region.get("biome") or "unknown")
            role = str(raw.get("terrain_role") or "memory_field")
            try:
                mass = max(0.0, min(1.0, float(raw.get("cognitive_mass", 0.0))))
                tree_suitability = max(
                    0.0, min(1.0, float(environment.get("tree_suitability", 0.0)))
                )
                rock_exposure = max(
                    0.0, min(1.0, float(environment.get("rock_exposure", 0.0)))
                )
                water_influence = max(
                    0.0, min(1.0, float(environment.get("water_influence", 0.0)))
                )
            except (TypeError, ValueError):
                continue
            zone = str(environment.get("ecological_zone") or "unknown")
            trees_allowed = bool(environment.get("trees_allowed", False))

            if role == "uplift":
                if (
                    biome in ROCK_BIOMES
                    and (rock_exposure >= 0.58 or zone in {"alpine_rock", "snowfield"})
                ):
                    for slot in range(2):
                        result.append(BuildCandidate(
                            entity_id=cls._stable_id(region_id, "rock", "uplift", slot),
                            entity_type="rock",
                            region_id=region_id,
                            role="uplift",
                            slot=slot,
                            cognitive_mass=mass,
                            environmental_zone=zone,
                            environmental_basis="rock_exposure",
                            environmental_score=rock_exposure,
                            priority=(0, -rock_exposure, -mass, region_id, slot),
                        ))
                elif trees_allowed and biome in TREE_BIOMES:
                    for slot in range(2):
                        result.append(BuildCandidate(
                            entity_id=cls._stable_id(region_id, "tree", "uplift", slot),
                            entity_type="tree",
                            region_id=region_id,
                            role="uplift",
                            slot=slot,
                            cognitive_mass=mass,
                            environmental_zone=zone,
                            environmental_basis="tree_suitability",
                            environmental_score=tree_suitability,
                            priority=(1, -tree_suitability, -mass, region_id, slot),
                        ))
            elif mass >= 0.75 and trees_allowed and biome in TREE_BIOMES:
                result.append(BuildCandidate(
                    entity_id=cls._stable_id(region_id, "tree", "recurrence", 0),
                    entity_type="tree",
                    region_id=region_id,
                    role="recurrence",
                    slot=0,
                    cognitive_mass=mass,
                    environmental_zone=zone,
                    environmental_basis="tree_suitability",
                    environmental_score=tree_suitability,
                    priority=(2, -tree_suitability, -mass, region_id, 0),
                ))

            if role == "basin" and biome in REST_BIOMES and water_influence >= 0.5:
                result.append(BuildCandidate(
                    entity_id=cls._stable_id(region_id, "rest_point", "basin", 0),
                    entity_type="rest_point",
                    region_id=region_id,
                    role="basin",
                    slot=0,
                    cognitive_mass=mass,
                    environmental_zone=zone,
                    environmental_basis="water_influence",
                    environmental_score=water_influence,
                    priority=(3, -water_influence, mass, region_id, 0),
                ))

        result.sort(key=lambda candidate: candidate.priority)
        return result[:MAX_CANDIDATES]

    def _builder_entity_count(self, regions: dict[str, dict[str, Any]]) -> int:
        count = 0
        for region_id in regions:
            for slot in range(2):
                for entity_type in ("tree", "rock"):
                    if self.store.entity_region(
                        self._stable_id(region_id, entity_type, "uplift", slot)
                    ) is not None:
                        count += 1
            for entity_type, role in (("tree", "recurrence"), ("rest_point", "basin")):
                if self.store.entity_region(
                    self._stable_id(region_id, entity_type, role, 0)
                ) is not None:
                    count += 1
        return count

    @staticmethod
    def _position(
        *,
        world_id: str,
        region: dict[str, Any],
        candidate: BuildCandidate,
    ) -> dict[str, float]:
        center = region["center"]
        radius = float(region["radius"])
        seed = sha256(
            f"{world_id}|{candidate.entity_id}|{AGENT_ID}".encode("utf-8")
        ).digest()
        angle_int = int.from_bytes(seed[:8], "big")
        radial_int = int.from_bytes(seed[8:16], "big")
        angle = (float(angle_int) / float(2**64 - 1)) * math.tau
        # Basins receive a rest point near the rim, never in the visual water.
        if candidate.role == "basin":
            radial = radius * (0.58 + 0.08 * (radial_int / float(2**64 - 1)))
        else:
            radial = radius * (0.34 + 0.18 * (radial_int / float(2**64 - 1)))
        return {
            "x": round(float(center["x"]) + math.cos(angle) * radial, 6),
            "y": round(float(center["y"]) + math.sin(angle) * radial, 6),
        }

    @staticmethod
    def _label(candidate: BuildCandidate) -> str:
        if candidate.entity_type == "tree":
            return "Árvore emergente"
        if candidate.entity_type == "rock":
            return "Afloramento rochoso"
        if candidate.entity_type == "rest_point":
            return "Marco de descanso"
        return "Elemento emergente"

    def _entity(
        self,
        *,
        world_id: str,
        logical_tick: int,
        projection_id: str,
        region: dict[str, Any],
        candidate: BuildCandidate,
    ) -> dict[str, Any]:
        return {
            "id": candidate.entity_id,
            "type": candidate.entity_type,
            "region_id": candidate.region_id,
            "position": self._position(
                world_id=world_id,
                region=region,
                candidate=candidate,
            ),
            "properties": {
                "label": self._label(candidate),
                "builder_origin": {
                    "agent_id": AGENT_ID,
                    "role": candidate.role,
                    "slot": candidate.slot,
                    "projection_id_at_creation": projection_id,
                    "logical_tick": int(logical_tick),
                    "environmental_zone": candidate.environmental_zone,
                    "environmental_basis": candidate.environmental_basis,
                    "environmental_score": round(candidate.environmental_score, 6),
                    "memory_is_authority": False,
                    "world_write_via_mutation_gate": True,
                },
            },
        }

    def evaluate_tick(self, logical_tick: int) -> list[dict[str, Any]]:
        logical_tick = int(logical_tick)
        if logical_tick <= 0 or logical_tick % self.interval_ticks != 0:
            return []

        world = self.world_provider()
        if not isinstance(world, dict):
            return [{"tick": logical_tick, "status": "world_unavailable"}]
        world_id = str(world.get("world_id") or "").strip()
        if not world_id:
            return [{"tick": logical_tick, "status": "world_unavailable"}]

        try:
            projection = self.reader.read(world_id)
        except (CognitiveTerrainError, OSError, ValueError) as exc:
            return [{
                "tick": logical_tick,
                "status": "projection_rejected",
                "error_type": type(exc).__name__,
            }]
        if projection is None:
            return [{"tick": logical_tick, "status": "projection_unavailable"}]

        try:
            environmental_state = derive_environmental_state(world, projection)
            environmental_regions = region_environment_map(environmental_state)
        except EnvironmentalRulesError as exc:
            return [{
                "tick": logical_tick,
                "status": "environment_rejected",
                "error_type": type(exc).__name__,
            }]

        regions = self._region_map(world)
        if self._builder_entity_count(regions) >= MAX_BUILDER_ENTITIES:
            return [{
                "tick": logical_tick,
                "status": "capacity_reached",
                "capacity": MAX_BUILDER_ENTITIES,
            }]
        candidates = self._candidate_specs(projection, regions, environmental_regions)
        if not candidates:
            return [{"tick": logical_tick, "status": "no_candidates"}]

        created: list[dict[str, Any]] = []
        projection_id = str(projection.get("projection_id") or "")
        environmental_state_id = str(environmental_state.get("state_id") or "")
        for candidate in candidates:
            if self.store.get_entity(candidate.entity_id) is not None:
                continue
            region = regions.get(candidate.region_id)
            if region is None:
                continue
            entity = self._entity(
                world_id=world_id,
                logical_tick=logical_tick,
                projection_id=projection_id,
                region=region,
                candidate=candidate,
            )
            result = self.guarded.commit(
                [{"op": "create", "entity": entity}],
                principal=self.principal,
                context={
                    "world_builder": {
                        "agent_id": AGENT_ID,
                        "logical_tick": logical_tick,
                        "projection_id": projection_id,
                        "candidate_id": candidate.entity_id,
                        "region_id": candidate.region_id,
                        "role": candidate.role,
                        "environmental_state_id": environmental_state_id,
                        "environmental_zone": candidate.environmental_zone,
                        "environmental_basis": candidate.environmental_basis,
                        "environmental_score": round(candidate.environmental_score, 6),
                        "memory_is_authority": False,
                    }
                },
                narration="",
            )
            if not result.get("ok"):
                created.append({
                    "tick": logical_tick,
                    "status": "rejected",
                    "entity_id": candidate.entity_id,
                    "region_id": candidate.region_id,
                    "role": candidate.role,
                    "reason": (result.get("decision") or {}).get("reason"),
                })
                break
            created.append({
                "tick": logical_tick,
                "status": "created",
                "entity_id": candidate.entity_id,
                "entity_type": candidate.entity_type,
                "region_id": candidate.region_id,
                "role": candidate.role,
                "projection_id": projection_id,
                "environmental_state_id": environmental_state_id,
                "environmental_zone": candidate.environmental_zone,
                "environmental_basis": candidate.environmental_basis,
                "environmental_score": round(candidate.environmental_score, 6),
                "world_event_id": (result.get("event") or {}).get("event_id"),
                "mutation_decision_id": (result.get("audit") or {}).get("decision_id")
                if isinstance(result.get("audit"), dict) else None,
            })
            if len([row for row in created if row["status"] == "created"]) >= self.max_creations_per_tick:
                break

        if created:
            return created
        return [{
            "tick": logical_tick,
            "status": "stable",
            "projection_id": projection_id,
            "environmental_state_id": environmental_state_id,
            "candidates": len(candidates),
        }]
