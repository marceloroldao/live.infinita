from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREVIEW = ROOT / "apps" / "renderer-godot" / "world_map_preview.gd"


class AtmosphericDepth008BQTests(unittest.TestCase):
    def test_depth_fog_is_non_volumetric_and_bounded(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        for expected in (
            "const ATMOSPHERIC_DEPTH_ENABLED := true",
            "const ATMOSPHERIC_FOG_DENSITY := 0.0026",
            "const ATMOSPHERIC_AERIAL_PERSPECTIVE := 0.32",
            "const ATMOSPHERIC_SKY_AFFECT := 0.48",
            "env.fog_enabled = true",
            "env.fog_density = ATMOSPHERIC_FOG_DENSITY",
            "env.fog_aerial_perspective = ATMOSPHERIC_AERIAL_PERSPECTIVE",
            "env.fog_sky_affect = ATMOSPHERIC_SKY_AFFECT",
        ):
            self.assertIn(expected, source)
        self.assertNotIn("env.volumetric_fog_enabled = true", source)

    def test_atmosphere_does_not_modify_world_or_geometry(self) -> None:
        source = PREVIEW.read_text(encoding="utf-8")
        section = source[source.index("var atmosphere := WorldEnvironment.new()"):source.index("_horizon_ground = MeshInstance3D.new()")]
        for forbidden in ("StaticBody3D", "CollisionShape3D", "GuardedMutationService", "move_and_slide"):
            self.assertNotIn(forbidden, section)


if __name__ == "__main__":
    unittest.main()
