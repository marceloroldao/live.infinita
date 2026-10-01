from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / 'apps' / 'renderer-godot'


class LocalDetourRouting008PTests(unittest.TestCase):
    def test_traversability_has_bounded_deterministic_detour_probes(self) -> None:
        source = (GODOT / 'world_map_traversability.gd').read_text(encoding='utf-8')
        self.assertIn('func find_detour(', source)
        self.assertIn('var probe_angles := [35.0, -35.0, 70.0, -70.0, 105.0, -105.0, 140.0, -140.0]', source)
        self.assertIn('validate_step(current, candidate, space_state)', source)
        self.assertIn('best["detour"] = true', source)
        self.assertIn('best["detour_angle_deg"] = float(angle)', source)

    def test_local_motion_only_detours_for_automatic_route(self) -> None:
        source = (GODOT / 'world_map_local_motion.gd').read_text(encoding='utf-8')
        self.assertIn('and auto_route and not manual', source)
        self.assertIn('_traversability.find_detour(', source)
        self.assertIn('policy["direct_block_reason"] = direct_reason', source)

    def test_manual_control_remains_direct_and_user_driven(self) -> None:
        source = (GODOT / 'world_map_local_motion.gd').read_text(encoding='utf-8')
        manual_idx = source.index('if manual:')
        detour_idx = source.index('_traversability.find_detour(')
        self.assertLess(manual_idx, detour_idx)
        self.assertIn('policy["manual"] = manual', source)

    def test_memory_projection_stays_non_authoritative(self) -> None:
        source = (GODOT / 'world_map_cognitive_terrain.gd').read_text(encoding='utf-8')
        self.assertIn('# Visual-only projection of bounded Memoria.ia aggregates.', source)
        self.assertIn('policy.get("world_write_authority", true) == false', source)
        self.assertNotIn('GuardedMutationService', source)


if __name__ == '__main__':
    unittest.main()
