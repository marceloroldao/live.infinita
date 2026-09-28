from __future__ import annotations

import math
from typing import Any


class NpcSocialOpportunity:
    """Read-only, region-bounded discovery of real social-capable entities.

    Capability and availability are explicit world evidence, not guesses about
    entity types. No actor is created and no relationship/satisfaction is assumed.
    """

    SCHEMA = "npc_social_opportunity_v1"

    def __init__(self, store: Any, regions: Any, *, max_candidates: int = 32,
                 max_regions: int = 8) -> None:
        self.store = store
        self.regions = regions
        self.max_candidates = max(1, int(max_candidates))
        self.max_regions = max(1, int(max_regions))

    @staticmethod
    def _position_is_valid(entity: dict[str, Any]) -> bool:
        position = entity.get("position")
        if not isinstance(position, dict):
            return False
        try:
            return all(
                not isinstance(position.get(axis), bool)
                and math.isfinite(float(position[axis]))
                for axis in ("x", "y")
            )
        except (ValueError, TypeError, KeyError, OverflowError):
            return False

    def discover(self, observer: dict[str, Any]) -> dict[str, Any]:
        observer_id = str(observer.get("id") or "").strip()
        region_id = str(observer.get("region_id") or "").strip()
        result: dict[str, Any] = {
            "schema": self.SCHEMA,
            "source": "live_cold_store_region_snapshot",
            "observer_id": observer_id,
            "observer_region_id": region_id,
            "region_ids": [],
            "region_scan_limited": False,
            "candidate_limit_reached": False,
            "candidate_ids": [],
            "evidence": [],
            "status": "observer_unavailable",
            "mutates_world": False,
        }
        if not observer_id or not region_id:
            return result
        region = self.regions.get(region_id) if callable(getattr(self.regions, "get", None)) else None
        if region is None:
            result["status"] = "region_unavailable"
            return result
        loader = getattr(self.store, "load_regions", None)
        if not callable(loader):
            result["status"] = "region_query_unavailable"
            return result
        region_ids = [region_id]
        # Only one topological hop; do not scan an unbounded persistent world.
        region_ids.extend(
            item for item in sorted(set(region.neighbors))
            if item != region_id and self.regions.get(item) is not None
        )
        result["region_scan_limited"] = len(region_ids) > self.max_regions
        region_ids = region_ids[:self.max_regions]
        result["region_ids"] = region_ids
        snapshots = loader(region_ids)
        if not isinstance(snapshots, list):
            result["status"] = "region_query_unavailable"
            return result
        accepted = {}
        for entity in snapshots:
            if not isinstance(entity, dict):
                continue
            candidate_id = str(entity.get("id") or "").strip()
            actual_region = str(entity.get("region_id") or "")
            if not candidate_id or candidate_id == observer_id or actual_region not in region_ids:
                continue
            props = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
            capabilities = props.get("interaction_capabilities")
            if not isinstance(capabilities, list) or "social" not in capabilities:
                continue
            if props.get("available_for_interaction") is not True:
                continue
            if not self._position_is_valid(entity):
                continue
            accepted[candidate_id] = {
                "entity_id": candidate_id,
                "region_id": actual_region,
                "capability": "social",
                "availability": "explicit_true",
                "source": "entity_properties",
            }
        result["candidate_limit_reached"] = len(accepted) > self.max_candidates
        evidence = [accepted[k] for k in sorted(accepted)[:self.max_candidates]]
        result["evidence"] = evidence
        result["candidate_ids"] = [row["entity_id"] for row in evidence]
        result["status"] = "observed" if evidence else "no_observed_social_actor"
        return result

    def candidates(self, observer: dict[str, Any]) -> list[str]:
        return list(self.discover(observer)["candidate_ids"])
