import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "ops-log-service" / "log_service.py"
spec = importlib.util.spec_from_file_location("ops_log_service", MODULE)
logs = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(logs)


class OpsLogServiceTest(unittest.TestCase):
    def test_sanitize_redacts_openai_and_token_like_values(self):
        value = logs.sanitize(
            "Authorization: Bearer abcdefghijklmnop api_key=secret-value sk-abcdefghijklmnopqrstuvwxyz"
        )
        self.assertNotIn("abcdefghijklmnop", value)
        self.assertNotIn("secret-value", value)
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", value)
        self.assertIn("REDACTED", value)

    def test_only_expected_units_are_exposed(self):
        self.assertEqual(set(logs.SERVICES), {"tiktok", "audio"})
        self.assertEqual(logs.SERVICES["tiktok"], "live-infinita-tiktok.service")
        self.assertEqual(logs.SERVICES["audio"], "live-infinita-audio.service")

    @patch.object(logs.subprocess, "run")
    def test_read_logs_clamps_lines_and_sanitizes(self, run):
        run.return_value.returncode = 0
        run.return_value.stdout = "x\napi_key=do-not-show\n"
        run.return_value.stderr = ""
        result = logs.read_logs("tiktok", 9999)
        self.assertTrue(result["ok"])
        self.assertNotIn("do-not-show", "\n".join(result["lines"]))
        command = run.call_args.args[0]
        self.assertIn(str(logs.MAX_LINES), command)


if __name__ == "__main__":
    unittest.main()
