from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from cognitive_shadow import summarize_shadow_file  # noqa: E402


class BoundedHealthMetricsTests(unittest.TestCase):
    def test_full_summary_stays_historical_tail_explicitly_recent(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "shadow.jsonl"
            with path.open("w", encoding="utf8") as fh:
                for n in range(300):
                    fh.write(json.dumps({
                        "id": n,
                        "label": "ação com caráter não ASCII",
                        "best_candidate": {"exact_structural_match": n % 2 == 0},
                        "contextual_forecast": {"status": "abstained"},
                        "contextual_evaluation": {"status": "abstained", "reason": "no_target"},
                    }, ensure_ascii=False) + "\n")
            full = summarize_shadow_file(path)
            tail = summarize_shadow_file(path, max_bytes=2048)
            self.assertEqual(full["records"], 300)
            self.assertLess(tail["records"], full["records"])
            self.assertGreater(tail["records"], 0)
            self.assertEqual(tail["last"]["id"], 299)
            self.assertEqual(tail["contextual_forecasts"], tail["records"])
            self.assertLessEqual(tail["records"], 20)
            self.assertEqual(full["last"]["id"], tail["last"]["id"])

    def test_window_discards_first_fragment_and_survives_truncated_tail(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "shadow.jsonl"
            with path.open("wb") as fh:
                fh.write((json.dumps({"id": 1, "payload": "x"*700})+"\n").encode())
                fh.write((json.dumps({"id": 2, "payload": "é"*60}, ensure_ascii=False)+"\n").encode())
                fh.write((json.dumps({"id": 3, "payload": "ok"})+"\n").encode())
                fh.write(b'{"incomplete":')
            recent = summarize_shadow_file(path, max_bytes=260)
            self.assertEqual(recent["last"]["id"], 3)
            self.assertGreaterEqual(recent["records"], 1)
            self.assertLessEqual(recent["records"], 2)

    def test_invalid_bounds_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "empty.jsonl"
            for bound in (0, -1, True):
                with self.subTest(bound=bound), self.assertRaises(ValueError):
                    summarize_shadow_file(path, max_bytes=bound)


if __name__ == "__main__":
    unittest.main()
