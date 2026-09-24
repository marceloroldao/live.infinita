from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from shadow_world_tick import _meaningful_boundary  # noqa: E402


class MemoriaV2ShadowBoundaryTests(unittest.TestCase):
    def test_uneventful_tick_is_not_persisted(self) -> None:
        self.assertFalse(_meaningful_boundary({
            "plans": [],
            "npc_needs": [],
            "npc_strategies": [],
            "npc_idle_wander": [],
            "events": [],
            "conditional_events": [],
        }))

    def test_running_plan_alone_is_not_a_persistence_boundary(self) -> None:
        self.assertFalse(_meaningful_boundary({
            "plans": [{"status": "running"}],
            "npc_needs": [],
            "npc_strategies": [],
            "npc_idle_wander": [],
            "events": [],
            "conditional_events": [],
        }))

    def test_completed_plan_is_a_persistence_boundary(self) -> None:
        self.assertTrue(_meaningful_boundary({"plans": [{"status": "completed"}]}))

    def test_world_event_is_a_persistence_boundary(self) -> None:
        self.assertTrue(_meaningful_boundary({"events": [{"scheduled_event_id": "night"}]}))

    def test_scheduled_need_is_a_persistence_boundary(self) -> None:
        self.assertTrue(_meaningful_boundary({"npc_needs": [{"status": "scheduled"}]}))


if __name__ == "__main__":
    unittest.main()
