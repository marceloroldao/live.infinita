"""Visual 001 Web deployment contract: isolate import, preserve Nov preview."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "deploy/visual-forest-web-root.sh"
WRAPPER = ROOT / "deploy/visual-forest-web.sh"


class ForestWebRolloutTests(unittest.TestCase):
    def test_operator_checks_clean_main_and_authenticates_in_tty(self):
        text = WRAPPER.read_text()
        for key in (
            'git -C "$REPO" pull --ff-only origin main',
            'sudo -v',
            'sudo -n -- bash',
            'tests.test_forest_stage_001',
            'tests.test_forest_web_rollout_001',
        ):
            self.assertIn(key, text)
        self.assertNotIn("sudo git ", text)

    def test_export_comes_from_exact_git_snapshot_not_live_project(self):
        text = SCRIPT.read_text()
        self.assertIn('archive "$SHA" apps/renderer-godot', text)
        self.assertIn('WORK="$(mktemp -d /var/tmp/', text)
        self.assertIn('PROJECT="$WORK/apps/renderer-godot"', text)
        self.assertIn('"$GODOT" --headless --editor --quit --path "$PROJECT"', text)
        self.assertIn('"$GODOT" --headless --path "$PROJECT" --export-release Web', text)
        self.assertIn('cmp -s "$PROJECT/diorama.gd"', text)
        self.assertIn('run/main_scene="res://main.tscn"', text)
        self.assertNotIn('rm -rf "$PROJECT_DIR/.godot"', text)
        self.assertNotIn(' --path "/opt/live.infinita/apps/renderer-godot"', text)
        self.assertNotIn(' --path "$WEB"', text)

    def test_rename_swap_and_preserved_independent_preview(self):
        text = SCRIPT.read_text()
        for key in (
            'mktemp -d /var/www/.live-infinita-godot.stage.',
            'mktemp -d /var/www/.live-infinita-godot.backup.',
            'cp -a -- "$WEB/nov-preview" "$STAGE/nov-preview"',
            'cmp -s "$STAGE/nov-preview/build.json"',
            'mv -T -- "$WEB" "$BACKUP/site"',
            'mv -T -- "$STAGE" "$WEB"',
            'FOREST001_WEB_ROLLBACK_STARTED',
            'FOREST001_WEB_ROLLBACK_OK',
            'FOREST001_WEB_BACKUP_PATH',
            'FOREST001_NOV_PREVIEW_PRESERVED',
            'FOREST001_WEB_RENAME_SWAP_OK',
        ):
            self.assertIn(key, text)
        self.assertNotIn('rsync -a --delete', text)
        self.assertNotIn('rm -rf "$WEB"', text)
        self.assertNotIn('systemctl reload nginx', text)

    def test_live_readback_and_no_other_service_restart(self):
        text = SCRIPT.read_text()
        self.assertIn('curl -fsS --max-time 12 --resolve live.etbra.com.br:443:127.0.0.1', text)
        self.assertIn('curl -fsSI --max-time 12 --resolve live.etbra.com.br:443:127.0.0.1', text)
        self.assertIn('"forest_stage": "visual-001"', text)
        for unit in (
            "live-infinita-renderer.service",
            "live-infinita-autonomous-world.service",
            "live-infinita-audio.service",
            "live-infinita-audio-web.service",
            "live-infinita-memoria-local.service",
        ):
            self.assertIn(unit, text)
        self.assertIn('BEFORE_PIDS["$svc"]', text)
        self.assertIn('FOREST001_NO_SERVICE_RESTART', text)
        self.assertNotIn("systemctl restart ", text)
        self.assertNotIn("systemctl enable ", text)
        self.assertNotIn("LIVE_INFINITA_SOURCE_SHA", text)


if __name__ == "__main__":
    unittest.main()
