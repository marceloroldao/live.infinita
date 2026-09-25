from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
PACKAGES = ROOT
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

conditional_module = load("conditional_event_scheduler_test_module", RUNTIME / "conditional_event_scheduler.py")
ConditionalEventScheduler = conditional_module.ConditionalEventScheduler
ConditionalEventError = conditional_module.ConditionalEventError


class FakeStore:
    def __init__(self):
        self.entities = {
            "nov": {"id": "nov", "region_id": "forest", "properties": {"awake": True}},
            "lamp": {"id": "lamp", "region_id": "village", "properties": {"lit": False}},
        }

    def get_entity(self, entity_id):
        value = self.entities.get(entity_id)
        return dict(value) if value else None


class FakeEngine:
    def __init__(self):
        self.cold_store = FakeStore()
        self.world = {"environment": {"period": "day"}, "state_hash": "h0"}
        self.sequence = 0

    def load_world(self):
        return dict(self.world)

    def commit_operations(self, operations, *, source, context, narration):
        self.sequence += 1
        for op in operations:
            if op.get("op") == "set_world":
                path = list(op.get("path") or [])
                if path == ["environment", "period"]:
                    self.world["environment"]["period"] = op.get("value")
            elif op.get("op") == "set":
                entity = self.cold_store.entities[op["entity_id"]]
                path = list(op.get("path") or [])
                if path == ["properties", "lit"]:
                    entity["properties"]["lit"] = op.get("value")
        self.world["state_hash"] = f"h{self.sequence}"
        event = {"event_id": f"evt_{self.sequence}"}
        delta = {"operations": operations}
        return event, delta, dict(self.world)


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


class ConditionalEventSchedulerTest(unittest.TestCase):
    def test_history_ignores_only_truncated_final_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            path = Path(tmp) / "conditional.jsonl"
            path.write_text('{"conditional_event_id":"cev_ok","status":"active"}\n{"conditional_event_id":', encoding="utf-8")
            scheduler = ConditionalEventScheduler(path, guarded)
            self.assertEqual(
                scheduler.history(),
                [{"conditional_event_id": "cev_ok", "status": "active"}],
            )
            self.assertEqual(
                path.read_text(encoding="utf-8"),
                '{"conditional_event_id":"cev_ok","status":"active"}\n',
            )
            self.assertEqual(
                path.with_suffix(".jsonl.truncated").read_text(encoding="utf-8"),
                '{"conditional_event_id":',
            )
            scheduler.register(
                condition={"kind": "world_equals", "path": ["environment", "period"], "value": "day"},
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "day"}],
                principal=PRINCIPAL,
            )
            self.assertEqual(len(scheduler.history()), 2)

    def test_history_rejects_corruption_before_final_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            path = Path(tmp) / "conditional.jsonl"
            path.write_text(
                '{"conditional_event_id":"cev_1","status":"active"}\n'
                '{"conditional_event_id":\n'
                '{"conditional_event_id":"cev_2","status":"active"}\n',
                encoding="utf-8",
            )
            scheduler = ConditionalEventScheduler(path, guarded)
            with self.assertRaises(json.JSONDecodeError):
                scheduler.history()

    def test_legacy_repair_removes_one_middle_fragment_and_preserves_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            path = Path(tmp) / "conditional.jsonl"
            original = (
                '{"conditional_event_id":"cev_1","status":"active"}\\n'
                '{"conditional_event_id":\\n'
                '{"conditional_event_id":"cev_2","status":"active"}\\n'
            )
            path.write_text(original, encoding="utf-8")
            scheduler = ConditionalEventScheduler(path, guarded)

            result = scheduler.repair_legacy_single_invalid_record()

            self.assertTrue(result["repaired"])
            self.assertEqual(result["removed_line"], 2)
            self.assertEqual(
                [row["conditional_event_id"] for row in scheduler.history()],
                ["cev_1", "cev_2"],
            )
            self.assertEqual(
                path.with_suffix(".jsonl.legacy-repair-v1.bak").read_text(encoding="utf-8"),
                original,
            )
            self.assertEqual(
                path.with_suffix(".jsonl.legacy-repair-v1.corrupt").read_text(encoding="utf-8"),
                '{"conditional_event_id":\\n',
            )
            self.assertFalse(scheduler.repair_legacy_single_invalid_record()["repaired"])

    def test_legacy_repair_rejects_multiple_invalid_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            path = Path(tmp) / "conditional.jsonl"
            path.write_text(
                '{"conditional_event_id":\\n'
                'not-json\\n'
                '{"conditional_event_id":"cev_2","status":"active"}\\n',
                encoding="utf-8",
            )
            scheduler = ConditionalEventScheduler(path, guarded)
            with self.assertRaises(ConditionalEventError):
                scheduler.repair_legacy_single_invalid_record()
            self.assertFalse(path.with_suffix(".jsonl.legacy-repair-v1.json").exists())

    def test_entity_region_edge_fires_once_until_false_then_true(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            row = scheduler.register(
                condition={"kind": "entity_in_region", "entity_id": "nov", "region_id": "village"},
                operations=[{"op": "set", "entity_id": "lamp", "path": ["properties", "lit"], "value": True}],
                principal=PRINCIPAL,
            )
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 0)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 1)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "forest"
            scheduler.evaluate_tick(4)
            guarded.engine.cold_store.entities["nov"]["region_id"] = "village"
            self.assertEqual(scheduler.evaluate_tick(5)[0]["fire_count"], 2)
            self.assertEqual(scheduler.get(row["conditional_event_id"])["last_fired_tick"], 5)

    def test_world_equals_one_shot(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                operations=[{"op": "set", "entity_id": "lamp", "path": ["properties", "lit"], "value": True}],
                principal=PRINCIPAL,
                one_shot=True,
            )
            scheduler.evaluate_tick(1)
            guarded.engine.world["environment"]["period"] = "night"
            result = scheduler.evaluate_tick(2)[0]
            self.assertEqual(result["status"], "completed")
            self.assertEqual(result["fire_count"], 1)
            self.assertTrue(guarded.engine.cold_store.entities["lamp"]["properties"]["lit"])
            self.assertEqual(scheduler.evaluate_tick(3), [])

    def test_level_mode_respects_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            guarded.engine.world["environment"]["period"] = "night"
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={"kind": "world_equals", "path": ["environment", "period"], "value": "night"},
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "night"}],
                principal=PRINCIPAL,
                trigger_mode="level",
                cooldown_ticks=3,
            )
            self.assertEqual(scheduler.evaluate_tick(1)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(2)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(3)[0]["fire_count"], 1)
            self.assertEqual(scheduler.evaluate_tick(4)[0]["fire_count"], 2)

    def test_entity_property_equals(self):
        with tempfile.TemporaryDirectory() as tmp:
            guarded = FakeGuarded()
            scheduler = ConditionalEventScheduler(Path(tmp) / "conditional.jsonl", guarded)
            scheduler.register(
                condition={"kind": "entity_property_equals", "entity_id": "nov", "path": ["properties", "awake"], "value": True},
                operations=[{"op": "set_world", "path": ["environment", "period"], "value": "day"}],
                principal=PRINCIPAL,
                one_shot=True,
            )
            result = scheduler.evaluate_tick(1)[0]
            self.assertEqual(result["fire_count"], 1)
            self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
