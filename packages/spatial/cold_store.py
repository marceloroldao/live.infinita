from __future__ import annotations

from collections import OrderedDict, defaultdict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


class FileRegionColdStore:
    """Persistent cold entity store partitioned by region.

    Full entity payloads live on disk. RAM keeps only a small manifest mapping
    entity ids to region ids plus region counts. Region payloads are loaded only
    when requested by the spatial candidate layer.
    """

    MANIFEST_VERSION = 1

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.regions_dir = self.root / "regions"
        self.manifest_file = self.root / "manifest.json"
        self.regions_dir.mkdir(parents=True, exist_ok=True)
        self._entity_region: dict[str, str] = {}
        self._region_counts: dict[str, int] = {}
        self._load_manifest()

    @staticmethod
    def _safe_region_filename(region_id: str) -> str:
        digest = hashlib.sha256(region_id.encode("utf-8")).hexdigest()
        return f"{digest}.json"

    def _region_file(self, region_id: str) -> Path:
        return self.regions_dir / self._safe_region_filename(region_id)

    @staticmethod
    def _atomic_write_json(path: Path, value: Any) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            fh.write("\n")
        tmp.replace(path)

    def _load_manifest(self) -> None:
        if not self.manifest_file.exists():
            self._entity_region = {}
            self._region_counts = {}
            return
        with self.manifest_file.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if int(payload.get("version", 0)) != self.MANIFEST_VERSION:
            raise ValueError("unsupported cold-store manifest version")
        self._entity_region = {str(k): str(v) for k, v in dict(payload.get("entity_region", {})).items()}
        self._region_counts = {str(k): int(v) for k, v in dict(payload.get("region_counts", {})).items()}

    def refresh_manifest(self) -> None:
        """Reload entity/region pointers after commits made by another process."""
        self._load_manifest()

    def _save_manifest(self) -> None:
        self._atomic_write_json(
            self.manifest_file,
            {
                "version": self.MANIFEST_VERSION,
                "entity_region": dict(sorted(self._entity_region.items())),
                "region_counts": dict(sorted(self._region_counts.items())),
                "entities_total": len(self._entity_region),
            },
        )

    def replace_all(self, entities: Iterable[dict[str, Any]]) -> None:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        entity_region: dict[str, str] = {}
        for raw in entities:
            entity = deepcopy(raw)
            entity_id = str(entity.get("id", "")).strip()
            region_id = str(entity.get("region_id", "")).strip()
            if not entity_id:
                raise ValueError("entity id is required")
            if not region_id:
                raise ValueError("entity region_id is required")
            if entity_id in entity_region:
                raise ValueError(f"duplicate entity id: {entity_id}")
            entity_region[entity_id] = region_id
            grouped[region_id].append(entity)

        for path in self.regions_dir.glob("*.json"):
            path.unlink()
        for region_id, rows in grouped.items():
            rows.sort(key=lambda row: str(row.get("id", "")))
            self._atomic_write_json(self._region_file(region_id), rows)

        self._entity_region = entity_region
        self._region_counts = {region_id: len(rows) for region_id, rows in grouped.items()}
        self._save_manifest()

    def load_region(self, region_id: str) -> list[dict[str, Any]]:
        path = self._region_file(region_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as fh:
            rows = json.load(fh)
        if not isinstance(rows, list):
            raise ValueError("invalid cold-store region payload")
        return [deepcopy(row) for row in rows if isinstance(row, dict)]

    def load_regions(self, region_ids: Iterable[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for region_id in sorted(set(str(value) for value in region_ids if str(value))):
            rows.extend(self.load_region(region_id))
        return rows

    def _write_region_rows(self, region_id: str, rows: list[dict[str, Any]]) -> None:
        rows = [deepcopy(row) for row in rows]
        rows.sort(key=lambda row: str(row.get("id", "")))
        path = self._region_file(region_id)
        if rows:
            self._atomic_write_json(path, rows)
            self._region_counts[region_id] = len(rows)
        else:
            if path.exists():
                path.unlink()
            self._region_counts.pop(region_id, None)

    def upsert(self, entity: dict[str, Any]) -> set[str]:
        value = deepcopy(entity)
        entity_id = str(value.get("id", "")).strip()
        region_id = str(value.get("region_id", "")).strip()
        if not entity_id:
            raise ValueError("entity id is required")
        if not region_id:
            raise ValueError("entity region_id is required")

        previous_region = self._entity_region.get(entity_id)
        touched: set[str] = {region_id}
        if previous_region:
            touched.add(previous_region)

        if previous_region and previous_region != region_id:
            previous_rows = [row for row in self.load_region(previous_region) if str(row.get("id", "")) != entity_id]
            self._write_region_rows(previous_region, previous_rows)

        rows = self.load_region(region_id)
        replaced = False
        for index, row in enumerate(rows):
            if str(row.get("id", "")) == entity_id:
                rows[index] = value
                replaced = True
                break
        if not replaced:
            rows.append(value)
        self._write_region_rows(region_id, rows)
        self._entity_region[entity_id] = region_id
        self._save_manifest()
        return touched

    def remove(self, entity_id: str) -> set[str]:
        entity_id = str(entity_id).strip()
        region_id = self._entity_region.pop(entity_id, None)
        if region_id is None:
            return set()
        rows = [row for row in self.load_region(region_id) if str(row.get("id", "")) != entity_id]
        self._write_region_rows(region_id, rows)
        self._save_manifest()
        return {region_id}

    def get_entity(self, entity_id: str) -> dict[str, Any] | None:
        region_id = self._entity_region.get(entity_id)
        if region_id is None:
            return None
        for entity in self.load_region(region_id):
            if str(entity.get("id", "")) == entity_id:
                return entity
        return None

    def entity_region(self, entity_id: str) -> str | None:
        return self._entity_region.get(entity_id)

    def entities_total(self) -> int:
        return len(self._entity_region)

    def region_count(self, region_id: str) -> int:
        return int(self._region_counts.get(region_id, 0))

    def stats(self) -> dict[str, Any]:
        return {
            "entities_total": len(self._entity_region),
            "regions_total": len(self._region_counts),
            "payload_resident_entities": 0,
        }


class ColdRegionCandidateCache:
    """Bounded LRU cache over cold region payloads."""

    def __init__(self, store: FileRegionColdStore, max_regions: int = 4) -> None:
        if max_regions < 1:
            raise ValueError("max_regions must be positive")
        self.store = store
        self.max_regions = int(max_regions)
        self._cache: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
        self.loads_total = 0
        self.hits_total = 0

    def _get_region(self, region_id: str) -> list[dict[str, Any]]:
        if region_id in self._cache:
            self.hits_total += 1
            rows = self._cache.pop(region_id)
            self._cache[region_id] = rows
            return rows
        rows = self.store.load_region(region_id)
        self.loads_total += 1
        self._cache[region_id] = rows
        while len(self._cache) > self.max_regions:
            self._cache.popitem(last=False)
        return rows

    def candidates(self, region_ids: Iterable[str]) -> dict[str, Any]:
        requested = sorted(set(str(value) for value in region_ids if str(value)))
        rows: list[dict[str, Any]] = []
        for region_id in requested:
            rows.extend(deepcopy(self._get_region(region_id)))
        return {
            "region_ids": requested,
            "entities": rows,
            "candidates_examined": len(rows),
            "resident_regions": list(self._cache.keys()),
            "resident_payload_entities": sum(len(value) for value in self._cache.values()),
            "store_entities_total": self.store.entities_total(),
            "loads_total": self.loads_total,
            "hits_total": self.hits_total,
        }

    def invalidate(self, region_ids: Iterable[str]) -> None:
        for region_id in set(str(value) for value in region_ids if str(value)):
            self._cache.pop(region_id, None)

    def clear(self) -> None:
        self._cache.clear()


def externalize_world_entities(world: dict[str, Any], store: FileRegionColdStore) -> dict[str, Any]:
    """Persist full entity payloads and return a cold-backed world envelope."""
    rows = [row for row in world.get("entities", []) if isinstance(row, dict)]
    store.replace_all(rows)
    result = deepcopy(world)
    result["entities"] = []
    cold = {
        "mode": "region_file_store",
        "entities_total": store.entities_total(),
        "regions_total": store.stats()["regions_total"],
        "payload_resident_entities": 0,
    }
    preferred = next(
        (
            str(row.get("id", ""))
            for row in rows
            if isinstance(row.get("properties"), dict) and bool(row["properties"].get("observer"))
        ),
        "",
    )
    if not preferred:
        preferred = next((str(row.get("id", "")) for row in rows if row.get("type") == "human"), "")
    if preferred:
        cold["default_observer_entity_id"] = preferred
    result["cold_entities"] = cold
    return result
