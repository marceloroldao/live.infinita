"""Visual-001 Web-only rollout: source, URL and rollback contract."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "deploy/visual-forest-web.sh"
ROOT_SCRIPT = ROOT / "deploy/visual-forest-web-root.sh"


class ForestWebRolloutTests(unittest.TestCase):
    def test_operator_sudo_is_explicit_and_git_is_unprivileged(self):
        script = WRAPPER.read_text()
        for marker in ("git -C \"$REPO\" pull --ff-only origin main",
                       "dirty_checkout", "sudo -v", "sudo -n -- bash",
                       "tests.test_forest_web_rollout"):
            self.assertIn(marker, script)
        self.assertNotIn("sudo git", script)
        self.assertNotIn("systemctl restart", script)

    def test_isolated_exact_git_export_never_touches_native_import_cache(self):
        script = ROOT_SCRIPT.read_text()
        for marker in (
            "git -c safe.directory=",
            'archive --format=tar "$SHA" apps/renderer-godot',
            'PROJECT="$WORK/apps/renderer-godot"',
            'cmp -s "$PROJECT/diorama.gd" "$INSTALL/diorama.gd"',
            'grep -Fq \'run/main_scene="res://main.tscn"\'',
            'timeout 600 nice -n 19 env GODOT_SILENCE_ROOT_WARNING=1',
            '--export-release Web "$BUILD/index.html"',
            'FOREST_WEB_ISOLATED_SOURCE_OK',
            'FOREST_WEB_ARTIFACT_OK',
            'FOREST_WEB_IMPORT_OK',
        ):
            self.assertIn(marker, script)
        self.assertNotIn('rm -rf "$INSTALL/.godot"', script)
        self.assertNotIn('--path "$INSTALL"', script)
        self.assertNotIn('rsync --delete', script)
        self.assertNotIn("export-godot-web.sh", script)

    def test_bounded_publication_and_verified_rollback(self):
        script = ROOT_SCRIPT.read_text()
        for marker in (
            "flock -n 9", 'FOREST_WEB_ROLLBACK_STARTED',
            'FOREST_WEB_ROLLBACK_OK', 'FOREST_WEB_RELEASE_READY',
            'mv -- "$WEB" "$BACKUP/previous"',
            'mv -- "$NEXT" "$WEB"',
            'mv -- "$BACKUP/previous" "$WEB"',
            "before_build=", 'FOREST_WEB_PUBLISHED_COMMIT_MISMATCH',
            'FOREST_WEB_PUBLISHED_OK', "index.wasm", "index.pck",
            'cp -a -- "$WEB/nov-preview" "$NEXT/nov-preview"',
            'FOREST_WEB_WORLD_RENDERER_AUDIO_UNCHANGED',
            '/api/health',
        ):
            self.assertIn(marker, script)
        self.assertIn('systemctl is-active --quiet "$BROADCASTER"', script)
        self.assertIn('systemctl show "$svc" -p MainPID --value', script)
        self.assertNotIn('systemctl restart', script)
        self.assertNotIn('systemctl reload nginx', script)
        self.assertNotIn('systemctl enable', script)
        self.assertNotIn('/var/lib/live-infinita/memoria-local', script)

    def test_build_is_2d_and_preserves_isolated_3d_preview(self):
        project = (ROOT / "apps/renderer-godot/project.godot").read_text()
        self.assertIn('run/main_scene="res://main.tscn"', project)
        self.assertNotIn('run/main_scene="res://forest_preview.tscn"', project)
        main = (ROOT / "apps/renderer-godot/main.tscn").read_text()
        self.assertIn('type="Node2D"', main)
        self.assertNotIn("forest_preview", main)


if __name__ == "__main__":
    unittest.main()
