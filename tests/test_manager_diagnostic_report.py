from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManagerDiagnosticReportTests(unittest.TestCase):
    def test_manager_exposes_report_workspace_and_send_controls(self) -> None:
        html = (ROOT / "apps" / "manager" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-page="relatorio"', html)
        self.assertIn('id="diagnostic-report"', html)
        self.assertIn('id="report-generate"', html)
        self.assertIn('id="report-copy"', html)
        self.assertIn('id="report-download"', html)

    def test_report_collects_critical_endpoints_without_failing_closed(self) -> None:
        source = (ROOT / "apps" / "manager" / "app.js").read_text(encoding="utf-8")
        self.assertIn("safeApi('/api/health')", source)
        self.assertIn("safeApi('/api/manage/monitor')", source)
        self.assertIn("safeApi('/api/audience/collective-intent')", source)
        self.assertIn("safeApi('/api/ops/logs/tiktok?lines=100')", source)
        self.assertIn("safeApi('/api/ops/logs/audio?lines=100')", source)
        self.assertIn("endpoint indisponível", source)

    def test_report_has_client_side_secret_redaction_and_omits_raw_comments(self) -> None:
        source = (ROOT / "apps" / "manager" / "app.js").read_text(encoding="utf-8")
        self.assertIn("sanitizeReportText", source)
        self.assertIn("[OPENAI_KEY_REMOVIDA]", source)
        self.assertIn("[TOKEN_REMOVIDO]", source)
        self.assertIn("[comentário da audiência omitido]", source)
        self.assertIn("Senha do Manager: NÃO incluída", source)
        self.assertIn("API keys / secrets: NÃO incluídos", source)
        self.assertNotIn("recent_comments:", source)


if __name__ == "__main__":
    unittest.main()
