"""Guard the opt-in read-only projection from the live Nov world stream."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCENE = ROOT / "apps/renderer-godot"


class NovMapReadOnlyTests(unittest.TestCase):
    def test_mapping_is_explicit_preview_not_new_authority(self):
        mapping = json.loads((SCENE / "nov_map_projection_001.json").read_text())
        self.assertEqual(mapping["schema"], "live-infinita-nov-visual-projection/v1")
        self.assertTrue(mapping["preview_only"])
        self.assertEqual(mapping["world_id"], "nov-live-autonomous-001")
        self.assertEqual(mapping["observer_entity_id"], "nov")
        self.assertEqual(mapping["map_grid_size"], 16)
        self.assertEqual(mapping["tile_size_m"], 64)
        self.assertEqual(set(mapping["anchors"]), {"shelter", "clearing", "deep_forest"})
        expected = {"shelter": (930, 390), "clearing": (640, 360),
                    "deep_forest": (350, 340)}
        for region, center in expected.items():
            self.assertEqual(tuple(mapping["anchors"][region]["world_center"]), center)
            cell = mapping["anchors"][region]["map_cell"]
            self.assertTrue(all(0 <= n < 16 for n in cell))

    def test_projection_validates_live_delivery_and_monotonicity(self):
        source = (SCENE / "nov_map_projection.gd").read_text()
        for token in ('"world_state"', '"world_id"', '"observer_entity_id"',
                      '"current_region_id"', '"sequence"', '"observer_outside_anchor"',
                      '"stale_sequence"', "last_sequence = int(sequence)"):
            self.assertIn(token, source)
        self.assertIn("message.get(\"delivery\")", source)
        for forbidden in ("WebSocket", "HTTPRequest", "FileAccess", "DirAccess",
                          "submit_intent", "set_world", "post_world"):
            self.assertNotIn(forbidden, source)

    def test_follow_is_opt_in_and_has_no_outbound_messages(self):
        client = (SCENE / "nov_map_follow.gd").read_text()
        preview = (SCENE / "world_map_preview.gd").read_text()
        self.assertIn('if str(argument) == "--follow-nov":', preview)
        self.assertIn("if _follow_nov:", preview)
        self.assertIn("NOV_MAP_FOLLOW_ACCEPTED", preview)
        self.assertIn("NOV_MAP_FOLLOW_READ_ONLY_ENABLED", preview)
        self.assertIn("MAX_MESSAGES_PER_FRAME := 12", client)
        self.assertIn("STALE_AFTER_MS := 15000", client)
        for forbidden in ("put_packet(", "send_text(", "send(", "interest_update",
                          "submit_intent", "post_world", "set_world"):
            self.assertNotIn(forbidden, client)
        self.assertNotIn("nov_map_follow", (SCENE / "main.tscn").read_text())

    def test_server_low_spec_profile_uses_bounded_multimesh_proxies(self):
        preview = (SCENE / "world_map_preview.gd").read_text()
        proxy = (SCENE / "world_map_proxy_foliage.gd").read_text()
        self.assertIn('if str(argument) == "--server-low-spec":', preview)
        self.assertIn("LOW_SPEC_DECOR_PER_TILE := 1", preview)
        self.assertIn("MAX_LOW_SPEC_PROXIES := 45", preview)
        self.assertIn('DETAIL_LAYER_NAME := "DetailedDecor"', preview)
        self.assertIn("return LOW_SPEC_DECOR_PER_TILE if cell == _focus_cell else 0", preview)
        self.assertIn("func _refresh_focus_detail(", preview)
        self.assertIn("_proxy_foliage.add_to_tile(", preview)
        self.assertIn("MultiMesh.new()", proxy)
        self.assertIn("MultiMeshInstance3D.new()", proxy)
        self.assertIn("MAX_PROXIES_PER_TILE := 5", proxy)
        self.assertIn("SHADING_MODE_UNSHADED", proxy)
        for forbidden in ("WebSocket", "HTTPClient", "FileAccess", "DirAccess",
                          "submit_intent", "post_world", "set_world"):
            self.assertNotIn(forbidden, proxy)

    def test_benchmark_is_explicit_and_bounded(self):
        preview = (SCENE / "world_map_preview.gd").read_text()
        self.assertIn('--benchmark-seconds=', preview)
        self.assertIn('--benchmark-fps=', preview)
        self.assertIn('clampf(raw_seconds.to_float(), 0.0, 60.0)', preview)
        self.assertIn('clampi(raw_fps.to_int(), 1, 60)', preview)
        self.assertIn('WORLD_MAP_BENCHMARK_RESULT', preview)
        self.assertIn('Engine.max_fps = _benchmark_target_fps', preview)

    def test_real_smoke_cases_present(self):
        projection = (ROOT / "tests/godot_nov_map_projection_smoke.gd").read_text()
        follower = (ROOT / "tests/godot_nov_map_follow_smoke.gd").read_text()
        self.assertIn("NOV_MAP_PROJECTION_SMOKE_OK", projection)
        self.assertIn("NOV_MAP_FOLLOW_SMOKE_OK", follower)
        self.assertIn("no_world_mutation=true", projection)
        self.assertIn("read_only=true", follower)


if __name__ == "__main__":
    unittest.main()
