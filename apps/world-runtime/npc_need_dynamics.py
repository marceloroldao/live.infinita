from __future__ import annotations

import json
import os
import time
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable


class NpcNeedDynamics:
    """Compact persistent need-state dynamics driven by logical world ticks.

    Current need state is checkpointed in a small JSON snapshot. Durable outcome
    idempotency/effects live in an append-only JSONL journal so the per-tick save
    never rewrites the entire historical outcome set.
    """

    DEFAULT_RATES = {
        "safety": -0.0030,
        "energy": 0.0020,
        "social": 0.0015,
        "curiosity": 0.0010,
    }

    def __init__(
        self,
        path: Path,
        store: Any,
        *,
        npc_ids: list[str],
        world_provider: Any | None = None,
        rates: dict[str, float] | None = None,
        outcome_journal_path: Path | None = None,
        stage_observer: Callable[[str, int], None] | None = None,
        monotonic_ns: Callable[[], int] = time.perf_counter_ns,
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.outcome_journal_path = (
            Path(outcome_journal_path)
            if outcome_journal_path is not None
            else self.path.with_suffix(".outcomes.jsonl")
        )
        self.store = store
        self.npc_ids = tuple(
            sorted({str(v).strip() for v in npc_ids if str(v).strip()})
        )
        self.world_provider = world_provider
        self.stage_observer = stage_observer
        self.monotonic_ns = monotonic_ns
        self.rates = dict(self.DEFAULT_RATES)
        for key, value in dict(rates or {}).items():
            if key in self.rates:
                self.rates[key] = float(value)

        loaded = self._load()
        legacy_outcomes = (
            dict(loaded.pop("applied_outcomes", {}))
            if isinstance(loaded.get("applied_outcomes"), dict)
            else {}
        )
        self._state = loaded
        self._outcome_rows = self._read_outcome_journal()
        self._applied_outcomes: dict[str, dict[str, Any]] = {
            str(row.get("outcome_id") or ""): deepcopy(row)
            for row in self._outcome_rows
            if str(row.get("outcome_id") or "")
        }

        if legacy_outcomes:
            self._migrate_legacy_outcomes(legacy_outcomes)
        else:
            self._recover_outcome_tail()

    def _stage(self, name: str, fn: Callable[[], Any]) -> Any:
        if self.stage_observer is None:
            return fn()
        started = self.monotonic_ns()
        try:
            return fn()
        finally:
            try:
                self.stage_observer(
                    name,
                    max(0, self.monotonic_ns() - started),
                )
            except Exception:
                pass

    @staticmethod
    def _clamp(value: float) -> float:
        return min(1.0, max(0.0, float(value)))

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schema": "npc_need_state_v2",
                "last_tick": 0,
                "npcs": {},
                "applied_outcome_rows": 0,
            }
        with self.path.open("r", encoding="utf-8") as fh:
            value = json.load(fh)
        if not isinstance(value, dict):
            raise ValueError("invalid NPC need dynamics state")
        value.setdefault("schema", "npc_need_state_v1")
        value.setdefault("last_tick", 0)
        value.setdefault("npcs", {})
        if "applied_outcomes" not in value:
            value.setdefault("applied_outcome_rows", 0)
        return value

    def _save(self) -> None:
        self._state["schema"] = "npc_need_state_v2"
        self._state.setdefault("applied_outcome_rows", len(self._outcome_rows))
        payload = {
            "schema": self._state["schema"],
            "last_tick": int(self._state.get("last_tick", 0)),
            "npcs": deepcopy(self._state.get("npcs", {})),
            "applied_outcome_rows": int(
                self._state.get("applied_outcome_rows", 0)
            ),
        }
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")

        def write_tmp() -> None:
            with tmp.open("w", encoding="utf-8") as fh:
                json.dump(
                    payload,
                    fh,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                fh.write("\n")

        self._stage("need.dynamics.save.write_tmp", write_tmp)
        self._stage("need.dynamics.save.replace", lambda: tmp.replace(self.path))

    def _read_outcome_journal(self) -> list[dict[str, Any]]:
        if not self.outcome_journal_path.exists():
            return []
        rows: list[dict[str, Any]] = []
        seen: dict[str, dict[str, Any]] = {}
        with self.outcome_journal_path.open("rb") as fh:
            for line_number, raw in enumerate(fh, start=1):
                if not raw.strip():
                    continue
                try:
                    row = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError(
                        f"corrupt NPC need outcome journal at line {line_number}"
                    ) from exc
                if not isinstance(row, dict):
                    raise ValueError(
                        f"invalid NPC need outcome journal row {line_number}"
                    )
                outcome_id = str(row.get("outcome_id") or "").strip()
                need = str(row.get("need") or "").strip().lower()
                npc_id = str(row.get("npc_id") or "").strip()
                if (
                    not outcome_id
                    or not npc_id
                    or need not in self.DEFAULT_RATES
                    or "after" not in row
                ):
                    raise ValueError(
                        f"invalid NPC need outcome journal row {line_number}"
                    )
                previous = seen.get(outcome_id)
                if previous is not None:
                    if previous != row:
                        raise ValueError(
                            f"conflicting duplicate NPC need outcome: {outcome_id}"
                        )
                    continue
                seen[outcome_id] = row
                rows.append(row)
        return rows

    def _replace_outcome_journal(self, rows: list[dict[str, Any]]) -> None:
        self.outcome_journal_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.outcome_journal_path.with_suffix(
            self.outcome_journal_path.suffix + ".tmp"
        )
        with tmp.open("wb") as fh:
            for row in rows:
                payload = (
                    json.dumps(
                        row,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                fh.write(payload)
            fh.flush()
            os.fsync(fh.fileno())
        tmp.replace(self.outcome_journal_path)
        folder_fd = os.open(
            str(self.outcome_journal_path.parent),
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0),
        )
        try:
            os.fsync(folder_fd)
        finally:
            os.close(folder_fd)

    def _migrate_legacy_outcomes(
        self,
        legacy_outcomes: dict[str, Any],
    ) -> None:
        legacy_rows: list[dict[str, Any]] = []
        legacy_ids: set[str] = set()
        for key, value in legacy_outcomes.items():
            if not isinstance(value, dict):
                continue
            row = deepcopy(value)
            outcome_id = str(
                row.get("outcome_id") or key or ""
            ).strip()
            if not outcome_id:
                continue
            row["outcome_id"] = outcome_id
            previous = self._applied_outcomes.get(outcome_id)
            if previous is not None and previous != row:
                raise ValueError(
                    f"legacy outcome conflicts with journal: {outcome_id}"
                )
            legacy_rows.append(row)
            legacy_ids.add(outcome_id)

        tail_rows = [
            deepcopy(row)
            for row in self._outcome_rows
            if str(row.get("outcome_id") or "") not in legacy_ids
        ]
        merged = legacy_rows + tail_rows
        if merged != self._outcome_rows:
            self._replace_outcome_journal(merged)

        self._outcome_rows = merged
        self._applied_outcomes = {
            str(row["outcome_id"]): deepcopy(row) for row in merged
        }

        # The legacy snapshot already contains all effects in legacy_rows.
        # Only a journal tail created after that checkpoint must be replayed.
        self._state["applied_outcome_rows"] = len(legacy_rows)
        self._recover_outcome_tail(force_save=True)

    def _recover_outcome_tail(self, *, force_save: bool = False) -> None:
        checkpoint = int(self._state.get("applied_outcome_rows", 0))
        if checkpoint < 0 or checkpoint > len(self._outcome_rows):
            raise ValueError("invalid NPC need outcome checkpoint")

        changed = False
        for row in self._outcome_rows[checkpoint:]:
            npc_id = str(row.get("npc_id") or "").strip()
            need = str(row.get("need") or "").strip().lower()
            npc_row = self._ensure_npc_row(npc_id)
            if npc_row is None:
                raise ValueError(
                    f"NPC not found while replaying outcome: {npc_id}"
                )
            needs = npc_row.setdefault("needs", {})
            needs[need] = self._clamp(float(row.get("after", 0.0)))
            changed = True

        if changed or force_save:
            self._state["applied_outcome_rows"] = len(self._outcome_rows)
            self._save()

    def _append_outcome(self, result: dict[str, Any]) -> None:
        payload = (
            json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        fd = os.open(
            self.outcome_journal_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND,
            0o644,
        )
        try:
            written = self._stage(
                "need.dynamics.outcome.write",
                lambda: os.write(fd, payload),
            )
            if written != len(payload):
                raise OSError(
                    f"short NPC need outcome append: {written}/{len(payload)}"
                )
            self._stage(
                "need.dynamics.outcome.fsync",
                lambda: os.fsync(fd),
            )
        finally:
            os.close(fd)
        self._outcome_rows.append(deepcopy(result))
        self._applied_outcomes[str(result["outcome_id"])] = deepcopy(result)

    def _entity(self, entity_id: str) -> dict[str, Any] | None:
        getter = getattr(self.store, "get_entity", None)
        if not callable(getter):
            return None
        return getter(entity_id)

    @staticmethod
    def _initial_needs(entity: dict[str, Any]) -> dict[str, float]:
        props = (
            entity.get("properties")
            if isinstance(entity.get("properties"), dict)
            else {}
        )
        raw = props.get("needs") if isinstance(props.get("needs"), dict) else {}
        result: dict[str, float] = {}
        for name in NpcNeedDynamics.DEFAULT_RATES:
            try:
                result[name] = NpcNeedDynamics._clamp(
                    float(raw.get(name, 0.0))
                )
            except (TypeError, ValueError):
                result[name] = 0.0
        return result

    def _ensure_npc_row(self, npc_id: str) -> dict[str, Any] | None:
        entity = self._entity(npc_id)
        if entity is None:
            return None
        npcs = self._state.setdefault("npcs", {})
        current = (
            npcs.get(npc_id)
            if isinstance(npcs.get(npc_id), dict)
            else None
        )
        if current is None:
            current = {
                "needs": self._initial_needs(entity),
                "last_tick": int(self._state.get("last_tick", 0)),
            }
            npcs[npc_id] = current
        return current

    def get_needs(self, npc_id: str) -> dict[str, float] | None:
        row = dict(self._state.get("npcs", {})).get(str(npc_id))
        if not isinstance(row, dict):
            return None
        raw = row.get("needs") if isinstance(row.get("needs"), dict) else {}
        return {
            name: self._clamp(raw.get(name, 0.0))
            for name in self.DEFAULT_RATES
        }

    def snapshot(self) -> dict[str, Any]:
        value = deepcopy(self._state)
        # Preserve the public snapshot contract without putting history back
        # into the hot checkpoint file.
        value["applied_outcomes"] = deepcopy(self._applied_outcomes)
        return value

    def satisfy(
        self,
        npc_id: str,
        need: str,
        amount: float,
        *,
        outcome_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Reduce one need exactly once for a durable outcome id."""
        npc_id = str(npc_id or "").strip()
        need = str(need or "").strip().lower()
        outcome_id = str(outcome_id or "").strip()
        if need not in self.DEFAULT_RATES:
            raise ValueError(f"unknown need: {need}")
        if not npc_id:
            raise ValueError("npc_id is required")
        if not outcome_id:
            raise ValueError("outcome_id is required")

        existing = self._applied_outcomes.get(outcome_id)
        if existing is not None:
            return deepcopy(existing)

        row = self._ensure_npc_row(npc_id)
        if row is None:
            raise ValueError(f"NPC not found: {npc_id}")
        needs = row.setdefault("needs", {})
        before = self._clamp(needs.get(need, 0.0))
        reduction = max(0.0, float(amount))
        after = self._clamp(before - reduction)
        result = {
            "outcome_schema": "npc_need_outcome_v1",
            "outcome_id": outcome_id,
            "npc_id": npc_id,
            "need": need,
            "amount": reduction,
            "before": before,
            "after": after,
            "metadata": deepcopy(metadata or {}),
        }

        # Journal first: a crash after the durable append but before checkpoint
        # save is recovered by replaying only the uncheckpointed journal tail.
        self._append_outcome(result)
        needs[need] = after
        self._state["applied_outcome_rows"] = len(self._outcome_rows)
        self._save()
        return deepcopy(result)

    def _same_region(
        self,
        entity: dict[str, Any],
        target_field: str,
    ) -> bool:
        props = (
            entity.get("properties")
            if isinstance(entity.get("properties"), dict)
            else {}
        )
        target_id = str(props.get(target_field) or "").strip()
        if not target_id:
            return False
        target = self._entity(target_id)
        if target is None:
            return False
        return str(target.get("region_id") or "") == str(
            entity.get("region_id") or ""
        )

    def _danger_level(self, entity: dict[str, Any]) -> float:
        props = (
            entity.get("properties")
            if isinstance(entity.get("properties"), dict)
            else {}
        )
        try:
            local = self._clamp(float(props.get("danger_level", 0.0)))
        except (TypeError, ValueError):
            local = 0.0
        world = 0.0
        if callable(self.world_provider):
            value = self.world_provider()
            env = (
                value.get("environment")
                if isinstance(value, dict)
                and isinstance(value.get("environment"), dict)
                else {}
            )
            try:
                world = self._clamp(float(env.get("danger_level", 0.0)))
            except (TypeError, ValueError):
                world = 0.0
        return max(local, world)

    def advance_tick(self, tick: int) -> list[dict[str, Any]]:
        tick = int(tick)
        last_tick = int(self._state.get("last_tick", 0))
        if tick <= last_tick:
            return []

        results: list[dict[str, Any]] = []
        npcs = self._state.setdefault("npcs", {})
        for npc_id in self.npc_ids:
            entity = self._entity(npc_id)
            if entity is None:
                continue
            current_row = (
                npcs.get(npc_id)
                if isinstance(npcs.get(npc_id), dict)
                else None
            )
            needs = (
                self._initial_needs(entity)
                if current_row is None
                else {
                    name: self._clamp(
                        (current_row.get("needs") or {}).get(name, 0.0)
                    )
                    for name in self.DEFAULT_RATES
                }
            )
            before = dict(needs)

            needs["safety"] = self._clamp(
                needs["safety"]
                + self.rates["safety"]
                + self._danger_level(entity) * 0.020
            )
            needs["energy"] = self._clamp(
                needs["energy"]
                + (
                    -0.020
                    if self._same_region(entity, "rest_target_entity_id")
                    else self.rates["energy"]
                )
            )
            needs["social"] = self._clamp(
                needs["social"]
                + (
                    -0.015
                    if self._same_region(entity, "social_target_entity_id")
                    else self.rates["social"]
                )
            )
            needs["curiosity"] = self._clamp(
                needs["curiosity"]
                + (
                    -0.020
                    if self._same_region(
                        entity, "curiosity_target_entity_id"
                    )
                    else self.rates["curiosity"]
                )
            )

            npcs[npc_id] = {"needs": needs, "last_tick": tick}
            results.append({
                "npc_id": npc_id,
                "tick": tick,
                "before": before,
                "after": dict(needs),
            })

        self._state["last_tick"] = tick
        self._stage("need.dynamics.advance.save", self._save)
        return results
