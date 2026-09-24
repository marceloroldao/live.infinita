from __future__ import annotations

import inspect
import math
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = ROOT / "apps" / "world-runtime"
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))

from npc_idle_wander import NpcIdleWander  # noqa: E402
from world_tick import WorldTickRunner  # noqa: E402


class NovWalkingPresentationTests(unittest.TestCase):
    def test_idle_wander_default_cadence_is_two_seconds_at_current_tick_rate(self) -> None:
        signature = inspect.signature(NpcIdleWander.__init__)
        self.assertEqual(signature.parameters["interval_ticks"].default, 4)
        stack_source = (RUNTIME_DIR / "npc_cognitive_stack.py").read_text(encoding="utf-8")
        self.assertIn("interval_ticks=4", stack_source)

    def test_consecutive_idle_waypoints_are_deterministic_and_visibly_separated(self) -> None:
        region = SimpleNamespace(center=(640.0, 360.0), radius=150.0)
        first = NpcIdleWander._waypoint("nov", region, 1)
        repeated = NpcIdleWander._waypoint("nov", region, 1)
        second = NpcIdleWander._waypoint("nov", region, 2)

        self.assertEqual(first, repeated)
        distance = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
        self.assertGreater(distance, 55.0)

    def test_only_a_scheduled_need_blocks_idle_walking(self) -> None:
        rows = [
            {"npc_id": "nov", "status": "cooldown"},
            {"npc_id": "nov", "status": "no_target"},
        ]
        self.assertEqual(WorldTickRunner._idle_blocked_npc_ids(rows), set())
        rows.append({"npc_id": "nov", "status": "scheduled"})
        self.assertEqual(WorldTickRunner._idle_blocked_npc_ids(rows), {"nov"})

    def test_godot_human_walk_uses_velocity_cadence_and_opposed_limbs(self) -> None:
        source = (ROOT / "apps" / "renderer-godot" / "entity_visual.gd").read_text(encoding="utf-8")
        self.assertIn("const HUMAN_WALK_SPEED := 48.0", source)
        self.assertIn("const HUMAN_WALK_ACCEL := 150.0", source)
        self.assertIn("func _advance_human_walk(delta: float)", source)
        self.assertIn("walk_velocity = walk_velocity.move_toward", source)
        self.assertIn("walk_phase = fmod", source)
        self.assertIn("var opposite := sin(walk_phase + PI)", source)
        self.assertIn("var arm_swing := opposite * 9.0", source)
        self.assertIn("facing_sign", source)

    def test_stationary_human_keeps_a_visible_idle_animation(self) -> None:
        source = (ROOT / "apps" / "renderer-godot" / "entity_visual.gd").read_text(encoding="utf-8")
        self.assertIn('entity_type == "human"', source)
        self.assertIn("var idle_breath := sin(visual_time * 1.8", source)
        self.assertIn("var idle_sway := sin(visual_time * 0.72", source)
        self.assertIn("Humans redraw even while stopped", source)

    def test_audio_service_uses_same_presentation_walk_speed(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita-audio.service").read_text(encoding="utf-8")
        self.assertIn('Environment="LIVE_INFINITA_WORLD_WALK_SPEED=48.0"', unit)


if __name__ == "__main__":
    unittest.main()
