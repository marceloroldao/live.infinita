"""Static gates for an opt-in renderer-only visual deployment."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OP = ROOT / "deploy/visual-forest-stage-001.sh"
PRIV = ROOT / "deploy/visual-forest-stage-001-root.sh"


class ForestRolloutContract(unittest.TestCase):
    def test_operator_keeps_git_and_auth_in_own_tty(self):
        c = OP.read_text()
        for required in ("git -C \"$REPO\" pull --ff-only origin main",
                         "sudo -v", "sudo -n -- bash",
                         "tests.test_forest_stage_001", "dirty_checkout"):
            self.assertIn(required, c)
        self.assertNotIn("systemctl restart", c)
        self.assertNotIn("sudo git ", c)

    def test_root_only_modifies_three_renderer_files_and_backups(self):
        c = PRIV.read_text()
        self.assertIn("FILES=(diorama.gd forest_preview.gd forest_preview.tscn)", c)
        self.assertIn('git -c safe.directory="$REPO"', c)
        self.assertIn('cp -a -- "$TARGET/diorama.gd" "$BACKUP/diorama.gd"', c)
        self.assertIn("FOREST001_ROLLBACK_OK", c)
        self.assertIn("FOREST001_NATIVE_DEPLOY_OK", c)
        self.assertIn("FOREST001_WORLD_AUDIO_UNCHANGED", c)
        self.assertIn("FOREST001_WEB_EXPORT_NOT_CHANGED", c)
        self.assertIn('systemctl restart "$RENDERER"', c)
        self.assertIn('systemctl is-active --quiet "$BROADCASTER"', c)
        self.assertIn('GODOT_SILENCE_ROOT_WARNING=1 "$GODOT" --headless --path "$STAGE"', c)
        self.assertNotIn(' --path "$TARGET"', c)
        self.assertNotIn("rsync --delete", c)
        self.assertNotIn("systemctl restart \"$WORLD\"", c)
        self.assertNotIn("systemctl restart \"$AUDIO\"", c)
        self.assertNotIn("systemctl restart \"$API\"", c)
        self.assertNotIn("export-godot-web.sh", c)

    def test_authoritative_world_and_broadcast_source_unchanged(self):
        renderer = (ROOT / "apps/renderer-godot/main.tscn").read_text()
        self.assertNotIn("forest_preview", renderer)
        self.assertIn('[node name="LiveInfinita" type="Node2D"]', renderer)
        self.assertNotIn('systemctl enable', PRIV.read_text())


if __name__ == "__main__":
    unittest.main()
