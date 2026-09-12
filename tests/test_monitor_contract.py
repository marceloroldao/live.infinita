from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "apps" / "renderer-web" / "monitor" / "index.html"
JS = ROOT / "apps" / "renderer-web" / "monitor" / "app.js"
CSS = ROOT / "apps" / "renderer-web" / "monitor" / "style.css"
SPATIAL_METRICS = ROOT / "apps" / "renderer-godot" / "spatial_metrics.gd"


class MonitorContractTest(unittest.TestCase):
    def test_monitor_assets_exist(self):
        self.assertTrue(INDEX.is_file())
        self.assertTrue(JS.is_file())
        self.assertTrue(CSS.is_file())
        self.assertTrue(SPATIAL_METRICS.is_file())

    def test_preview_uses_clean_capture_mode(self):
        html = INDEX.read_text(encoding="utf-8")
        self.assertIn('/godot/?capture=1', html)
        self.assertNotIn('guides=1', html)

    def test_operator_key_is_not_persisted(self):
        js = JS.read_text(encoding="utf-8")
        lowered = js.lower()
        self.assertNotIn('localstorage', lowered)
        self.assertNotIn('sessionstorage', lowered)
        self.assertIn('Authorization:', js)
        self.assertIn('Bearer ${token}', js)
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

    def test_spatial_metrics_are_monitor_only_and_same_origin(self):
        html = INDEX.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        gd = SPATIAL_METRICS.read_text(encoding="utf-8")
        self.assertIn('id="spatial-hot"', html)
        self.assertIn('id="spatial-warm"', html)
        self.assertIn('id="spatial-hit-rate"', html)
        self.assertIn("event.origin !== window.location.origin", js)
        self.assertIn("live-infinita-spatial-metrics", js)
        self.assertIn("window.parent.postMessage", gd)
        self.assertIn("window.location.origin", gd)
        self.assertNotIn("LIVE_INFINITA_STREAM_OUTPUT", gd)
        self.assertNotIn("Authorization", gd)

    def test_spatial_history_is_bounded_and_memory_only(self):
        html = INDEX.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        lowered = js.lower()
        self.assertIn('id="spatial-history"', html)
        self.assertIn('HISTORY_MAX_SAMPLES = 240', js)
        self.assertIn('HISTORY_MIN_SAMPLE_MS = 5000', js)
        self.assertIn('while (spatialHistory.length > HISTORY_MAX_SAMPLES)', js)
        self.assertIn('spatialHistory.length = 0', js)
        self.assertNotIn('indexeddb', lowered)
        self.assertNotIn('localstorage', lowered)
        self.assertNotIn('sessionstorage', lowered)


if __name__ == "__main__":
    unittest.main()
