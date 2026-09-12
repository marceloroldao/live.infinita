from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "apps" / "renderer-web" / "monitor" / "index.html"
JS = ROOT / "apps" / "renderer-web" / "monitor" / "app.js"
CSS = ROOT / "apps" / "renderer-web" / "monitor" / "style.css"


class MonitorContractTest(unittest.TestCase):
    def test_monitor_assets_exist(self):
        self.assertTrue(INDEX.is_file())
        self.assertTrue(JS.is_file())
        self.assertTrue(CSS.is_file())

    def test_preview_uses_clean_capture_mode(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('/godot/?capture=1', html)
        self.assertNotIn('guides=1', html)

    def test_operator_key_is_not_persisted(self):
        js = JS.read_text(encoding="utf-8")
        lowered = js.lower()
        self.assertNotIn('localstorage', lowered)
        self.assertNotIn('sessionstorage', lowered)
        self.assertIn('Bearer ${operatorToken}', js)
        self.assertIn("operatorToken = ''", js)

    def test_monitor_cannot_start_external_broadcast(self):
        combined = INDEX.read_text(encoding="utf-8") + JS.read_text(encoding="utf-8")
        self.assertNotIn('LIVE_INFINITA_STREAM_OUTPUT', combined)
        self.assertNotIn('systemctl', combined)
        self.assertNotIn('/api/simulate', combined)
        self.assertNotIn('/api/world/reset', combined)

    def test_program_audio_is_explicit_user_action(self):
        html = INDEX.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertIn('id="audio"', html)
        self.assertIn("audioButton.addEventListener('click', toggleAudio)", js)


if __name__ == "__main__":
    unittest.main()
