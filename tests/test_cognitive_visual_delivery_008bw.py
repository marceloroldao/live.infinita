from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROJECTION = ROOT / "apps" / "world-runtime" / "cognitive_terrain_projection.py"
SPATIAL = ROOT / "apps" / "world-runtime" / "main_spatial.py"
RENDERER = ROOT / "apps" / "renderer-godot" / "world_map_cognitive_terrain.gd"


class CognitiveVisualDelivery008BWTests(unittest.TestCase):
    def test_projection_persists_visual_state_in_same_atomic_file(self) -> None:
        source = PROJECTION.read_text(encoding="utf-8")
        block = source[source.index("def project_once("):source.index("class CognitiveTerrainProjectionReader")]
        self.assertIn("previous_projection = _read_json(", block)
        self.assertIn("stabilize_visual_projection(projection, previous_projection)", block)
        self.assertIn("_atomic_write(output_path, projection)", block)
        self.assertLess(
            block.index("stabilize_visual_projection(projection, previous_projection)"),
            block.index("_atomic_write(output_path, projection)"),
        )

    def test_reader_validates_optional_visual_budgets(self) -> None:
        source = PROJECTION.read_text(encoding="utf-8")
        section = source[source.index("def _validate(value"):source.index("def read(", source.index("def _validate(value"))]
        for expected in (
            'visual_id = value.get("visual_projection_id")',
            'visual_regions = value.get("visual_regions")',
            'visual_transitions = value.get("visual_transitions")',
            'visual_spatial_trails = value.get("visual_spatial_trails")',
            "len(visual_regions) > MAX_REGIONS",
            "len(visual_transitions) > MAX_TRANSITIONS",
            "len(visual_spatial_trails) > MAX_SPATIAL_TRAILS",
        ):
            self.assertIn(expected, section)

    def test_websocket_environment_uses_visual_regions_only_for_delivery(self) -> None:
        source = SPATIAL.read_text(encoding="utf-8")
        helper = source[source.index("def _visual_environment_projection"):source.index("def _client_world_payload")]
        self.assertIn('visual_regions = projection.get("visual_regions")', helper)
        self.assertIn('visual["regions"] = visual_regions', helper)
        self.assertIn('visual["projection_id"] = visual_id', helper)
        delivery = source[source.index("def _client_world_payload"):source.index("async def spatial_broadcast")]
        self.assertIn("_visual_environment_projection(projection)", delivery)
        # Raw projection is still delivered unchanged for diagnosis/world rendering metadata.
        self.assertIn('delivery["cognitive_terrain"] = projection', delivery)

    def test_renderer_gates_on_visual_id_and_consumes_visual_arrays(self) -> None:
        source = RENDERER.read_text(encoding="utf-8")
        self.assertIn('var _visual_projection_id := ""', source)
        self.assertIn("func visual_projection_id() -> String:", source)
        self.assertIn('projection.get("visual_projection_id", next_id)', source)
        self.assertIn("next_visual_id == _visual_projection_id", source)
        self.assertIn('projection.get("visual_regions", projection.get("regions", []))', source)
        self.assertIn('"visual_transitions"', source)
        self.assertIn('"visual_spatial_trails"', source)
        self.assertIn("_projection_id = next_id", source)
        self.assertIn("_visual_projection_id = next_visual_id", source)


if __name__ == "__main__":
    unittest.main()
