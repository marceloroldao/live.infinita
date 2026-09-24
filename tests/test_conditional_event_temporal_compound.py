from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


module = load("conditional_event_temporal_test_module", RUNTIME / "conditional_event_scheduler.py")
ConditionalEventScheduler = module.ConditionalEventScheduler


class FakeStore:
    def __init__(self):
        self.entities = {
            "nov": {"id": "nov", "type": "human", "region_id": "village", "position": {"x": 0, "y": 0}, "properties": {}},
            "fire": {"id": "fire", "type": "fire", "region_id": "village", "position": {"x": 10, "y": 0}, "properties": {"lit": True}},
            "npc": {"id": "npc", "type": "human", "region_id": "village", "position": {"x": 12, "y": 0}, "properties": {}},
        }

    def get_entity(self, entity_id):
        value = self.entities.get(entity_id)
        return dict(value) if value else None

    def load_region(self, region_id):
        return [dict(v) for v in self.entities.values() if v.get("region_id") == region_id]


class FakeEngine:
    def __init__(self):
        self.cold_store = FakeStore()
        self.world = {"environment": {"period": "day", "weather": "clear", "visibility": 1.0}, "state_hash": "h0"}
        self.sequence = 0

    def load_world(self):
        return self.world

    def commit_operations(self, operations, *, source, context, narration):
        self.sequence += 1
        for op in operations:
            if op.get("op") == "set_world":
                path = list(op.get("path") or [])
                if path[:1] == ["environment"] and len(path) == 2:
                    self.world["environment"][path[1]] = op.get("value")
            elif op.get("op") == "set":
                entity = self.cold_store.entities[op["entity_id"]]
                path = list(op.get("path") or [])
                if path[:1] == ["properties"] and len(path) == 2:
                    entity.setdefault("properties", {})[path[1]] = op.get("value")
        self.world["state_hash"] = f"h{self.sequence}"
        return {"event_id": f"evt_{self.sequence}"}, {"operations": operations}, self.world


class FakeGate:
    def decide(self, operations, principal):
        from packages.spatial import MutationDecision, MutationPrincipal
        if isinstance(principal, dict):
            principal = MutationPrincipal.from_dict(principal)
        return MutationDecision(True, "accepted", principal, tuple(operations))


class FakeGuarded:
    def __init__(self):
        from mutation_gate_service import GuardedMutationService
        self.service = GuardedMutationService(FakeEngine(), gate=FakeGate())

    def __getattr__(self, name):
        return getattr(self.service, name)


PRINCIPAL = {"source": "system", "actor_id": "world", "authority": "system"}


class ConditionalTemporalCompoundTest(unittest.TestCase):
    def test_sustain_ticks_requires_continuous_truth_and_resets(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            row = scheduler.register(
                condition={"kind": "entity_in_region", "entity_id": "nov", "region_id": "village", "sustain_ticks": 3},
                operations=[{"op": "set_world", "path": ["environment", "visibility"], "value": 0.8}],
                principal=PRINCIPAL,
                one_shot=True,
            )
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 0)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "forest"
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 0)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(4)[0]["fire_count"], 0)
            fired = scheduler.evaluate_tick(5)[0]
            self.assertEqual(fired["fire_count"], 1)
            self.assertEqual(fired["status"], "completed")
            self.assertEqual(scheduler.get(row["conditional_event_id"])["true_since_tick"], 3)

    def test_all_condition_rain_and_night(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={
                    "kind": "all",
                    "conditions": [
                        {"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                        {"kind": "world_equals", "path": ["environment", "weather"], "value": "rain"},
                    ],
                },
                operations=[{"op": "set_world", "path": ["environment", "visibility"], "value": 0.45}],
                principal=PRINCIPAL,
                one_shot=True,
            )
            scheduler.evaluate_tick(1)
            guarded.engine.world["environment"]["period"] = "night"
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 0)
            guarded.engine.world["environment"]["weather"] = "rain"
            result = scheduler.evaluate_tick(3)[0]
            self.assertEqual(result["fire_count"], 1)
            self.assertEqual(guarded.engine.world["environment"]["visibility"], 0.45)

    def test_nobody_near_fire_for_four_ticks(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={
                    "kind": "nobody_near_entity",
                    "anchor_entity_id": "fire",
                    "radius": 8,
                    "entity_types": ["human"],
                    "sustain_ticks": 4,
                },
                operations=[{"op": "set", "entity_id": "fire", "path": ["properties", "lit"], "value": False}],
                principal=PRINCIPAL,
                one_shot=True,
            )
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 0)
            guarded.engine.cold_store.entities["npc"]["position"] = {"x": 100, "y": 100}
            guarded.engine.cold_store.entities["nov"]["position"] = {"x": 100, "y": 100}
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 0)
            self.assertEqual(scheduler.evaluate_tick(4)[0]["fire_count"], 0)
            result = scheduler.evaluate_tick(5)[0]
            self.assertEqual(result["fire_count"], 1)
            self.assertFalse(guarded.engine.cold_store.entities["fire"]["properties"]["lit"])

    def test_level_compound_respects_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            guarded.engine.world["environment"].update({"period": "night", "weather": "rain"})
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={
                    "kind": "all",
                    "conditions": [
                        {"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                        {"kind": "world_equals", "path": ["environment", "weather"], "value": "rain"},
                    ],
                },
                operations=[{"op": "set_world", "path": ["environment", "visibility"], "value": 0.5}],
                principal=PRINCIPAL,
                trigger_mode="level",
                cooldown_ticks=3,
            )
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(4)[0]["fire_count"], 2)


if __name__ == "__main__":
    unittest.main()
