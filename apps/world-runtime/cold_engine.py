from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any

from packages.spatial import FileRegionColdStore, externalize_world_entities


class ColdAuthoritativeWorldEngine:
    """Authoritative engine whose entity payloads live in region cold storage.

    The resident world document contains region/environment metadata plus a
    cold-entity envelope, but no full entity list. Entity operations are applied
    directly to FileRegionColdStore. State integrity uses a deterministic delta
    hash chain so commits do not require rehydrating the universe.
    """

    def __init__(self, bootstrap_file: Path, data_dir: Path, cold_store: FileRegionColdStore) -> None:
        self.bootstrap_file = Path(bootstrap_file)
        self.data_dir = Path(data_dir)
        self.world_file = self.data_dir / "world.json"
        self.events_file = self.data_dir / "events.jsonl"
        self.deltas_file = self.data_dir / "deltas.jsonl"
        self.cold_store = cold_store
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.world_file.exists():
            bootstrap = self._load_json(self.bootstrap_file)
            world = externalize_world_entities(bootstrap, self.cold_store)
            world["version"] = int(world.get("version", 0))
            world["sequence"] = 0
            world["state_hash"] = self._bootstrap_hash(world)
            self._save_json(self.world_file, world)
        else:
            world = self._load_json(self.world_file)
            cold = world.get("cold_entities") if isinstance(world.get("cold_entities"), dict) else {}
            if cold.get("mode") != "region_file_store" or world.get("entities") not in ([], None):
                raise ValueError("cold engine requires a migrated cold-backed world.json")
            if not self.cold_store.manifest_file.exists():
                raise ValueError("cold engine requires an existing cold-store manifest")

    @staticmethod
    def _load_json(path: Path) -> dict[str, Any]:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    @staticmethod
    def _save_json(path: Path, value: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(value, fh, ensure_ascii=False, sort_keys=True, indent=2)
            fh.write("\n")
        tmp.replace(path)

    @staticmethod
    def _canonical(value: Any) -> bytes:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")

    @classmethod
    def _bootstrap_hash(cls, world: dict[str, Any]) -> str:
        clean = copy.deepcopy(world)
        clean.pop("state_hash", None)
        return hashlib.sha256(b"cold-bootstrap-v1\0" + cls._canonical(clean)).hexdigest()

    @classmethod
    def _next_hash(cls, previous_hash: str, delta: dict[str, Any]) -> str:
        clean = copy.deepcopy(delta)
        clean.pop("result_hash", None)
        payload = previous_hash.encode("ascii") + b"\0" + cls._canonical(clean)
        return hashlib.sha256(b"cold-delta-v1\0" + payload).hexdigest()

    def load_world(self) -> dict[str, Any]:
        return self._load_json(self.world_file)

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        return self.cold_store.get_entity(entity_id)

    def propose(self, world: dict[str, Any], action: str, source: str = "runtime", context: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
        action = action.strip().lower()
        sequence = int(world.get("sequence", 0)) + 1
        event = {
            "event_id": f"evt_{sequence:06d}",
            "sequence": sequence,
            "type": "validated_action",
            "action": action,
            "source": source,
            "context": context or {},
        }
        operations: list[dict[str, Any]] = []
        narration = ""

        if action == "spawn_person":
            if self._entity("person_01") is None:
                region_id = self.cold_store.entity_region("tree_01") or self.cold_store.entity_region("fire_01")
                if not region_id:
                    raise ValueError("região de spawn não encontrada")
                operations.append({"op": "append_entity", "value": {
                    "id": "person_01", "type": "human", "region_id": region_id,
                    "position": {"x": 650, "y": 320}, "scale": 1.0,
                    "properties": {"label": "Visitante"},
                }})
                narration = "Um visitante entra silenciosamente na clareira."
            else:
                narration = "O visitante já está na clareira."
        elif action == "move_tree":
            tree = self._entity("tree_01")
            if tree is None:
                raise ValueError("tree_01 não existe")
            x = int(tree.get("position", {}).get("x", 220))
            operations.append({"op": "set", "path": ["entities", "tree_01", "position", "x"], "value": 360 if x < 300 else 220})
            narration = "A árvore muda de posição no estado do mundo."
        elif action == "toggle_fire":
            fire = self._entity("fire_01")
            if fire is None:
                raise ValueError("fire_01 não existe")
            lit = not bool(fire.get("properties", {}).get("lit", True))
            operations.append({"op": "set", "path": ["entities", "fire_01", "properties", "lit"], "value": lit})
            narration = "A fogueira se acende." if lit else "A fogueira se apaga."
        elif action in {"set_day", "set_night"}:
            period = "day" if action == "set_day" else "night"
            operations.append({"op": "set", "path": ["environment", "period"], "value": period})
            narration = "A luz do dia retorna à clareira." if period == "day" else "A noite cai sobre a clareira."
        elif action == "reset":
            operations.append({"op": "replace_world_from_bootstrap"})
            narration = "O mundo retorna ao estado inicial."
        else:
            raise ValueError(f"ação desconhecida: {action}")

        delta = {
            "delta_id": f"delta_{sequence:06d}",
            "event_id": event["event_id"],
            "sequence": sequence,
            "from_version": int(world.get("version", 0)),
            "to_version": int(world.get("version", 0)) + 1,
            "operations": operations,
            "narration": narration,
        }
        return event, delta

    @staticmethod
    def _set_nested(target: dict[str, Any], keys: list[Any], value: Any) -> None:
        cursor: Any = target
        for key in keys[:-1]:
            if not isinstance(cursor, dict):
                raise ValueError("caminho inválido")
            cursor = cursor.setdefault(key, {})
        if not isinstance(cursor, dict):
            raise ValueError("caminho inválido")
        cursor[keys[-1]] = copy.deepcopy(value)

    def _apply_entity_operation(self, operation: dict[str, Any]) -> None:
        op = operation.get("op")
        if op == "append_entity":
            value = operation.get("value")
            if not isinstance(value, dict):
                raise ValueError("append_entity sem payload")
            self.cold_store.upsert(value)
            return
        path = operation.get("path", [])
        if not (isinstance(path, list) and len(path) >= 2 and path[0] == "entities"):
            raise ValueError("operação de entidade inválida")
        entity_id = str(path[1])
        if op == "remove":
            self.cold_store.remove(entity_id)
            return
        if op != "set":
            raise ValueError(f"operação cold desconhecida: {op}")
        entity = self._entity(entity_id)
        if entity is None:
            raise ValueError(f"entidade ausente: {entity_id}")
        if len(path) < 3:
            raise ValueError("set de entidade requer subcaminho")
        self._set_nested(entity, path[2:], operation.get("value"))
        self.cold_store.upsert(entity)

    def apply_delta(self, world: dict[str, Any], delta: dict[str, Any], *, mutate_store: bool = True) -> dict[str, Any]:
        result = copy.deepcopy(world)
        previous_hash = str(world.get("state_hash", ""))
        for operation in delta.get("operations", []):
            op = operation.get("op")
            path = operation.get("path", [])
            if op == "replace_world_from_bootstrap":
                bootstrap = self._load_json(self.bootstrap_file)
                if mutate_store:
                    result = externalize_world_entities(bootstrap, self.cold_store)
                else:
                    result = copy.deepcopy(bootstrap)
                    result["entities"] = []
                    result["cold_entities"] = copy.deepcopy(world.get("cold_entities", {}))
                continue
            if op == "append_entity" or (isinstance(path, list) and path and path[0] == "entities"):
                if mutate_store:
                    self._apply_entity_operation(operation)
                continue
            if op == "set":
                self._set_nested(result, list(path), operation.get("value"))
                continue
            raise ValueError(f"operação desconhecida: {op}")

        result["entities"] = []
        result["version"] = int(delta["to_version"])
        result["sequence"] = int(delta["sequence"])
        result.setdefault("narration", {})["text"] = delta.get("narration", "")
        result["last_event"] = {"event_id": delta["event_id"], "sequence": delta["sequence"]}
        cold = result.setdefault("cold_entities", {})
        cold.update({
            "mode": "region_file_store",
            "entities_total": self.cold_store.entities_total() if mutate_store else int(cold.get("entities_total", 0)),
            "regions_total": self.cold_store.stats()["regions_total"] if mutate_store else int(cold.get("regions_total", 0)),
            "payload_resident_entities": 0,
        })
        result["state_hash"] = self._next_hash(previous_hash, delta)
        return result

    def commit_action(self, action: str, source: str = "runtime", context: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        world = self.load_world()
        event, delta = self.propose(world, action, source=source, context=context)
        new_world = self.apply_delta(world, delta, mutate_store=True)
        delta["result_hash"] = new_world["state_hash"]
        self._append_jsonl(self.events_file, event)
        self._append_jsonl(self.deltas_file, delta)
        self._save_json(self.world_file, new_world)
        return event, delta, new_world

    def replay_hash(self) -> str:
        bootstrap = self._load_json(self.bootstrap_file)
        envelope = copy.deepcopy(bootstrap)
        envelope["entities"] = []
        envelope["cold_entities"] = {
            "mode": "region_file_store",
            "entities_total": len([row for row in bootstrap.get("entities", []) if isinstance(row, dict)]),
            "regions_total": len({str(row.get("region_id", "")) for row in bootstrap.get("entities", []) if isinstance(row, dict)}),
            "payload_resident_entities": 0,
        }
        envelope["version"] = int(envelope.get("version", 0))
        envelope["sequence"] = 0
        state_hash = self._bootstrap_hash(envelope)
        for delta in self.read_jsonl(self.deltas_file):
            clean = copy.deepcopy(delta)
            clean.pop("result_hash", None)
            state_hash = self._next_hash(state_hash, clean)
        return state_hash

    def verify_replay(self) -> dict[str, Any]:
        current = self.load_world()
        replay_hash = self.replay_hash()
        return {
            "ok": current.get("state_hash") == replay_hash,
            "current_hash": current.get("state_hash"),
            "replay_hash": replay_hash,
            "events": len(self.read_jsonl(self.events_file)),
            "deltas": len(self.read_jsonl(self.deltas_file)),
            "version": current.get("version"),
            "sequence": current.get("sequence"),
        }
