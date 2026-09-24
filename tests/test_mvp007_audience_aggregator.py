from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "apps" / "audience" / "aggregator.py"
spec = importlib.util.spec_from_file_location("audience_aggregator", MODULE)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)
AudienceAggregator = module.AudienceAggregator


class AudienceAggregatorTest(unittest.TestCase):
    def test_ten_joins_create_one_pending_proposal(self):
        agg = AudienceAggregator()
        proposals = []
        for i in range(10):
            proposals.extend(agg.ingest({"kind": "join", "received_at_unix": 1000 + i}, now=1000 + i))
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["rule_id"], "joins-10-30s")
        self.assertEqual(proposals[0]["proposed_action"], "spawn_person")
        self.assertEqual(proposals[0]["status"], "pending")

    def test_nine_joins_do_not_trigger(self):
        agg = AudienceAggregator()
        proposals = []
        for i in range(9):
            proposals.extend(agg.ingest({"kind": "join"}, now=2000 + i))
        self.assertEqual(proposals, [])

    def test_fifty_likes_create_toggle_fire_proposal(self):
        agg = AudienceAggregator()
        proposals = []
        for i in range(50):
            proposals.extend(agg.ingest({"kind": "like"}, now=3000 + (i * 0.1)))
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["proposed_action"], "toggle_fire")

    def test_gift_creates_proposal_without_mutating_world(self):
        agg = AudienceAggregator()
        proposals = agg.ingest({"kind": "gift"}, now=4000)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0]["status"], "pending")

    def test_old_events_are_pruned_instead_of_growing_forever(self):
        agg = AudienceAggregator()
        for second in range(5000):
            agg.ingest({"kind": "like"}, now=float(second))
        # At one event/second and a 30s maximum window, only roughly the live window remains.
        self.assertLessEqual(agg.retained_event_count(), 31)

    def test_threshold_can_trigger_again_after_window_expires(self):
        agg = AudienceAggregator()
        first = []
        for i in range(10):
            first.extend(agg.ingest({"kind": "join"}, now=1000 + i))
        self.assertEqual(len(first), 1)

        # Advance beyond the 30-second window, then form a new independent group.
        agg.ingest({"kind": "join"}, now=1100)
        second = []
        for i in range(1, 10):
            second.extend(agg.ingest({"kind": "join"}, now=1100 + i))
        self.assertEqual(len(second), 1)

    def test_late_event_keeps_window_order_valid(self):
        agg = AudienceAggregator()
        agg.ingest({"kind": "join"}, now=100)
        agg.ingest({"kind": "join"}, now=102)
        agg.ingest({"kind": "join"}, now=101)
        self.assertEqual(agg.retained_event_count(), 3)


if __name__ == "__main__":
    unittest.main()
