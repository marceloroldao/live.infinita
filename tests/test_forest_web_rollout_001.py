"""Contract for exact-source, rollback-capable Web-only forest deployment."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
OP = (ROOT / "deploy/visual-forest-web-rollout.sh").read_text()
ROOT_SCRIPT = (ROOT / "deploy/visual-forest-web-rollout-root.sh").read_text()


class ForestWebRolloutTests(unittest.TestCase):
    def test_operator_keeps_git_credentials_and_auth_on_own_tty(self):
        for marker in (
            'git -C "$REPO" pull --ff-only origin main',
            'git -C "$REPO" rev-parse origin/main',
            "sudo -v",
            "sudo -n -- bash",
            "tests.test_forest_stage_001",
            "FOREST_WEB_OPERATOR_LOG_READY",
        ):
            self.assertIn(marker, OP)
        self.assertNotIn("sudo git ", OP)
        self.assertNotIn("systemctl restart", OP)

    def test_export_is_isolated_from_native_project_and_from_world(self):
        for marker in (
            'git -c safe.directory="$REPO" -C "$REPO" archive "$SHA" apps/renderer-godot',
            'PROJECT="$WORK/apps/renderer-godot"',
            '--editor --quit --path "$PROJECT"',
            '--export-release Web "$WORK/build/index.html"',
            'FOREST_WEB_SNAPSHOT_OK',
            'FOREST_WEB_ASSETS_IMPORTED',
            'FOREST_WEB_EXPORT_OK',
        ):
            self.assertIn(marker, ROOT_SCRIPT)
        self.assertNotIn(' --path "/opt/live.infinita/apps/renderer-godot"', ROOT_SCRIPT)
        self.assertNotIn('rm -rf "$PROJECT/.godot"', ROOT_SCRIPT)
        self.assertNotIn("bash deploy/update.sh", ROOT_SCRIPT)
        self.assertNotIn("systemctl restart ", ROOT_SCRIPT)
        self.assertNotIn("systemctl reload ", ROOT_SCRIPT)
        self.assertNotIn("rsync --delete", ROOT_SCRIPT)

    def test_site_swap_preserves_nov_preview_and_restores_on_failure(self):
        for marker in (
            'cp -a -- "$WEB/nov-preview" "$CANDIDATE/nov-preview"',
            'cmp -s "$BACKUP/site/nov-preview/build.json" "$WEB/nov-preview/build.json"',
            'mv -T -- "$WEB" "$BACKUP/site"',
            'mv -T -- "$CANDIDATE" "$WEB"',
            'mv -T -- "$BACKUP/site" "$WEB"',
            "FOREST_WEB_ROLLBACK_OK",
            "FOREST_WEB_ATOMIC_PUBLISH_OK",
            "FOREST_WEB_NATIVE_WORLD_AUDIO_UNCHANGED",
            "FOREST_WEB_NOV_PREVIEW_PRESERVED",
        ):
            self.assertIn(marker, ROOT_SCRIPT)

    def test_public_build_identity_verified_via_local_nginx(self):
        self.assertIn('--resolve live.etbra.com.br:443:127.0.0.1', ROOT_SCRIPT)
        self.assertIn('"$PUBLIC_SHA" == "$SHA"', ROOT_SCRIPT)
        for file in ("index.html", "index.js", "index.pck", "index.wasm"):
            self.assertIn(file, ROOT_SCRIPT)
        self.assertIn('"source_commit": sys.argv[2]', ROOT_SCRIPT)
        self.assertIn('"scenario": "forest-stage-001"', ROOT_SCRIPT)
        self.assertIn('grep -Fq "FOREST_TREE_COUNT := 17"', ROOT_SCRIPT)
        self.assertIn('run/main_scene="res://main.tscn"', ROOT_SCRIPT)
        self.assertNotIn("nov_memory_continuous.py", ROOT_SCRIPT)

    def test_expected_export_preset_and_visual_scene(self):
        p = (ROOT / "apps/renderer-godot")
        self.assertIn('name="Web"', (p / "export_presets.cfg").read_text())
        self.assertIn('run/main_scene="res://main.tscn"', (p / "project.godot").read_text())
        self.assertIn("FOREST_TREE_COUNT := 17", (p / "diorama.gd").read_text())
        self.assertNotIn("forest_preview", (p / "main.tscn").read_text())
        catalog = json.loads((p / "assets/quaternius/stylized_nature_megakit/catalog.json").read_text())
        self.assertEqual(catalog["license"], "CC0-1.0")


if __name__ == "__main__":
    unittest.main()
