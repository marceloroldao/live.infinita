from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any


class DeterministicWorldEngine:
    def __init__(self, bootstrap_file: Path, data_dir: Path) -> None:
        self.bootstrap_file = bootstrap_file
        self.data_dir = data_dir
        self.world_file = data_dir / "world.json"
        self.events_file = data_dir / "events.jsonl"
        self.deltas_file = data_dir / "deltas.jsonl"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        if not self.world_file.exists():
            world = self._load_json(self.bootstrap_file)
            world["version"] = int(world.get("version", 0))
            world["sequence"] = 0
            world["state_hash"] = self.hash_world(world)
            self._save_json(self.world_file, world)

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
    def hash_world(world: dict[str, Any]) -> str:
        clean = copy.deepcopy(world)
        clean.pop("state_hash", None)
        payload = json.dumps(clean, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def load_world(self) -> dict[str, Any]:
        return self._load_json(self.world_file)

    def _append_jsonl(self, path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    @staticmethod
    def _find_entity(world: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
        for entity in world.get("entities", []):
            if entity.get("id") == entity_id:
                return entity
        return None

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
            if self._find_entity(world, "person_01") is None:
                operations.append({"op": "append_entity", "value": {"id": "person_01", "type": "human", "position": {"x": 650, "y": 320}, "scale": 1.0, "properties": {"label": "Visitante"}}})
                narration = "Um visitante entra silenciosamente na clareira."
            else:
                narration = "O visitante já está na clareira."
        elif action == "move_tree":
            tree = self._find_entity(world, "tree_01")
            if tree is None:
                raise ValueError("tree_01 não existe")
            x = int(tree.get("position", {}).get("x", 220))
            operations.append({"op": "set", "path": ["entities", "tree_01", "position", "x"], "value": 360 if x < 300 else 220})
            narration = "A árvore muda de posição no estado do mundo."
        elif action == "toggle_fire":
            fire = self._find_entity(world, "fire_01")
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

    def apply_delta(self, world: dict[str, Any], delta: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(world)
        for operation in delta.get("operations", []):
            op = operation.get("op")
            if op == "replace_world_from_bootstrap":
                result = self._load_json(self.bootstrap_file)
                continue
            if op == "append_entity":
                result.setdefault("entities", []).append(copy.deepcopy(operation["value"]))
                continue
            if op == "set":
                path = operation["path"]
                if path[0] == "entities":
                    entity = self._find_entity(result, path[1])
                    if entity is None:
                        raise ValueError(f"entidade ausente: {path[1]}")
                    target: Any = entity
                    keys = path[2:]
                else:
                    target = result
                    keys = path
                for key in keys[:-1]:
                    target = target.setdefault(key, {})
                target[keys[-1]] = copy.deepcopy(operation["value"])
                continue
            raise ValueError(f"operação desconhecida: {op}")

        result["version"] = int(delta["to_version"])
        result["sequence"] = int(delta["sequence"])
        result.setdefault("narration", {})["text"] = delta.get("narration", "")
        result["last_event"] = {"event_id": delta["event_id"], "sequence": delta["sequence"]}
        result["state_hash"] = self.hash_world(result)
        return result

    def commit_action(self, action: str, source: str = "runtime", context: dict[str, Any] | None = None) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        world = self.load_world()
        event, delta = self.propose(world, action, source=source, context=context)
        new_world = self.apply_delta(world, delta)
        delta["result_hash"] = new_world["state_hash"]
        self._append_jsonl(self.events_file, event)
        self._append_jsonl(self.deltas_file, delta)
        self._save_json(self.world_file, new_world)
        return event, delta, new_world

    def read_jsonl(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def replay(self) -> dict[str, Any]:
        world = self._load_json(self.bootstrap_file)
        world["version"] = int(world.get("version", 0))
        world["sequence"] = 0
        world["state_hash"] = self.hash_world(world)
        for delta in self.read_jsonl(self.deltas_file):
            world = self.apply_delta(world, delta)
        return world

    def verify_replay(self) -> dict[str, Any]:
        current = self.load_world()
        replayed = self.replay()
        return {
            "ok": current.get("state_hash") == replayed.get("state_hash"),
            "current_hash": current.get("state_hash"),
            "replay_hash": replayed.get("state_hash"),
            "events": len(self.read_jsonl(self.events_file)),
            "deltas": len(self.read_jsonl(self.deltas_file)),
            "version": current.get("version"),
            "sequence": current.get("sequence"),
        }
