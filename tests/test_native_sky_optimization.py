from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
GODOT = ROOT / "apps/renderer-godot"


class NativeSkyOptimizationContract(unittest.TestCase):
    def test_original_web_shader_remains_the_default(self):
        main = (GODOT / "main.gd").read_text(encoding="utf-8")
        assert 'sky_material.shader = preload("res://story_sky_native.gdshader") if native_fast_sky else preload("res://story_sky.gdshader")' in main
        self.assertIn('not OS.has_feature("web")', main)
        self.assertIn('OS.get_environment("LIVE_INFINITA_RENDER_FAST_SKY") == "1"', main)
        unit = (ROOT / "deploy/live-infinita-renderer.service").read_text(encoding="utf-8")
        self.assertIn("Environment=LIVE_INFINITA_RENDER_FAST_SKY=1", unit)

    def test_native_sky_preserves_palette_and_gradient_with_cheap_dither(self):
        old = (GODOT / "story_sky.gdshader").read_text(encoding="utf-8")
        native = (GODOT / "story_sky_native.gdshader").read_text(encoding="utf-8")
        self.assertIn("fract(sin(dot(FRAGCOORD.xy", old)
        self.assertNotIn("sin(", native)
        for line in (
            "vec3 top = mix(",
            "vec3 bottom = mix(",
            "bottom = mix(bottom,",
            "vec3 sky = mix(top, bottom, smoothstep(0.0, 0.64, UV.y));",
            "COLOR = vec4(sky + (dither - 0.5) / 255.0, 1.0);",
        ):
            self.assertIn(line, old)
            self.assertIn(line, native)
        self.assertIn("mod(floor(FRAGCOORD.xy), 4.0)", native)
        # Both dither values lie in [0,1). Their maximum per-channel
        # difference is below one 8-bit display level.
        samples = [(x * 0.75487766 + y * 0.56984029) % 1.0
                   for y in range(4) for x in range(4)]
        self.assertEqual(len(set(round(v, 7) for v in samples)), 16)
        self.assertTrue(all(0.0 <= v < 1.0 for v in samples))

    def test_static_sky_geometry_is_constructed_once(self):
        source = (GODOT / "main.gd").read_text(encoding="utf-8")
        self.assertEqual(source.count("\n    _build_sky_geometry()\n"), 1)
        self.assertIn("sky_stars.append(Vector2(x, y))", source)
        self.assertIn("sky_cloud_contours.append(contour)", source)
        draw = source.split("func _draw_sky(", 1)[1]
        self.assertIn("draw_circle(sky_stars[i]", draw)
        self.assertIn("draw_colored_polygon(sky_cloud_contours[i], cloud)", draw)
        self.assertNotIn("for point in range(40)", draw)
        self.assertNotIn("43758.5453", draw)


if __name__ == "__main__":
    unittest.main()
