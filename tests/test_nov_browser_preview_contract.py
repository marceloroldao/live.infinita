"""Independent Nov preview must never replace the existing /godot/ broadcast."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPORT = ROOT / "deploy/export-nov-preview-web.sh"
BROADCAST_EXPORT = ROOT / "deploy/export-godot-web.sh"
PROJECT = ROOT / "apps/renderer-godot/project.godot"
PREVIEW = ROOT / "apps/renderer-godot/nov_character_preview.tscn"


class NovBrowserPreviewContract(unittest.TestCase):
    def test_exporter_is_separate_and_stages_preview_in_existing_web_root(self):
        source = EXPORT.read_text(encoding="utf-8")
        self.assertIn('PREVIEW_NAME="nov-preview"', source)
        self.assertIn('if [[ ! -s "$WEB_ROOT/index.html" ]]', source)
        self.assertIn("rsync -a --exclude '/.godot/'", source)
        self.assertIn('run/main_scene="res://nov_character_preview.tscn"', source)
        self.assertIn('run/main_scene="res://main.tscn"', source)
        self.assertIn('mv -- "$STAGE" "$TARGET"', source)
        self.assertIn('--export-release "Web"', source)
        self.assertNotIn('systemctl restart', source)
        self.assertNotIn('nginx_godot_patch.py', source)
        self.assertNotIn('rm -rf "$WEB_ROOT"', source)

    def test_broadcast_export_protects_preview_from_rsync_delete(self):
        source = BROADCAST_EXPORT.read_text(encoding="utf-8")
        self.assertIn("rsync -a --delete --exclude '/nov-preview/'", source)
        self.assertIn("--exclude '/.nov-preview.*/'", source)

    def test_production_scene_remains_unchanged(self):
        self.assertIn('run/main_scene="res://main.tscn"', PROJECT.read_text())
        self.assertTrue(PREVIEW.is_file())


if __name__ == "__main__":
    unittest.main()
