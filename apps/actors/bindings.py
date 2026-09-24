from __future__ import annotations

import json
from pathlib import Path
import time
from typing import Any


class BindingConflict(ValueError):
    pass


class ActorBindingStore:
    """One actor per entity, with an append-only operator history.

    Callers serialize writes and validate actor/entity existence. This MVP runs
    in a single runtime worker, just like the world and audience stores.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def history(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        with self.path.open(encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]

    def current(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for row in self.history():
            if row["operation"] == "bind":
                result[row["actor_key"]] = row["entity_id"]
            else:
                result.pop(row["actor_key"], None)
        return result

    def _append(self, operation: str, actor_key: str, entity_id: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "operation": operation,
            "actor_key": actor_key,
            "entity_id": entity_id,
            "changed_at_unix": time.time(),
            "provenance": {"channel": "operator-api", "operator": "shared-token"},
        }
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")

    def bind(self, actor_key: str, entity_id: str) -> bool:
        current = self.current()
        if current.get(actor_key) == entity_id:
            return False
        if actor_key in current:
            raise BindingConflict("participante já vinculado; desvincule antes de trocar")
        if entity_id in current.values():
            raise BindingConflict("personagem já vinculado a outro participante")
        self._append("bind", actor_key, entity_id)
        return True

    def unbind(self, actor_key: str, entity_id: str) -> bool:
        current = self.current()
        if actor_key not in current:
            return False
        if current[actor_key] != entity_id:
            raise BindingConflict("vínculo atual é diferente do personagem informado")
        self._append("unbind", actor_key, entity_id)
        return True
