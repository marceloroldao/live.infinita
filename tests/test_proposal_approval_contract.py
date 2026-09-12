from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "apps" / "world-runtime" / "main_spatial.py").read_text(encoding="utf-8")


class ProposalApprovalContractTest(unittest.TestCase):
    def test_audience_commit_requires_operator_bearer(self) -> None:
        self.assertIn("audience_proposal_commit_requires_operator", SOURCE)
        self.assertIn("/api/audience/proposals/", SOURCE)
        self.assertIn("WWW-Authenticate", SOURCE)
        self.assertIn("compare_digest", SOURCE)

    def test_operator_approval_marker_is_internal_only(self) -> None:
        self.assertIn('metadata["operator_approved"] = True', SOURCE)
        self.assertIn('metadata.get("operator_approved") and metadata.get("proposal_id")', SOURCE)
        self.assertIn('authority = "operator"', SOURCE)

    def test_direct_audience_remains_proposal_only(self) -> None:
        self.assertIn('normalized_source in {"tiktok", "youtube"}', SOURCE)
        self.assertIn('authority = "audience"', SOURCE)


if __name__ == "__main__":
    unittest.main()
