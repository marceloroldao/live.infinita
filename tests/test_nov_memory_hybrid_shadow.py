"""Hybrid Nov recall preserves baseline overlap while covering real outcomes."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_hybrid_shadow import select_hybrid, OwnerHybridRecallWorker, RecallBlocked
from nov_memory_recall_shadow import select_related
from nov_trajectory_recall_shadow import trajectory_signature


def row(label: str, tick: int, *, need: str = "hunger",
        region: str = "forest", satisfaction: float = 0.5) -> dict:
    return {
        "record_key": label * 64, "logical_tick": tick,
        "addresses": {"need": need, "region_id": region, "weather": "sun"},
        "observation": {
            "logical_tick": tick, "need": need,
            "context": {"region_id": region, "weather": "sun"},
            "outcome": {
                "satisfaction": satisfaction, "observed_risk": 0.1,
                "elapsed_ticks": 1, "preemptions": 0, "replans": 0,
            },
        },
    }


class HybridSelectionTests(unittest.TestCase):
    def test_relevance_vector_is_identical_while_outcome_diversity_grows(self):
        data = [
            row("a", 1, region="shelter", satisfaction=0.1),
            row("b", 2, region="shelter", satisfaction=0.2),
            row("c", 3, region="forest", satisfaction=0.1),
            row("d", 4, region="forest", satisfaction=0.1),
            row("e", 5, region="forest", satisfaction=0.1),
            row("f", 6, region="forest", satisfaction=0.1),
            row("g", 7, region="forest", satisfaction=0.2),
            row("h", 8, region="forest", satisfaction=0.2),
        ]
        query = {"need": "hunger", "region_id": "forest", "weather": "sun"}
        selected, result = select_hybrid(data, query=query, exclude_key=None)
        baseline, matched = select_related(data, query=query, exclude_key=None, limit=5)
        self.assertEqual(result["matching_records"], matched)
        self.assertEqual(result["baseline_overlap_counts"],
                         [len(row["matching_addresses"]) for row in baseline])
        self.assertEqual(result["hybrid_overlap_counts"],
                         [len(row["matching_addresses"]) for row in selected])
        self.assertEqual(result["baseline_full_matches"], result["hybrid_full_matches"])
        self.assertTrue(result["relevance_vector_preserved"])
        self.assertGreaterEqual(result["hybrid_trajectory_profiles"],
                                result["baseline_trajectory_profiles"])
        self.assertFalse(result["selection_authority"])
        self.assertFalse(result["new_evidence_created"])
        self.assertNotIn("hunger", json.dumps(result))
        self.assertNotIn("shelter", json.dumps(result))
        self.assertNotIn("record_key", json.dumps(result))

    def test_anchor_is_stable_and_diversity_only_within_same_band(self):
        data = [
            row("a", 1, region="forest", satisfaction=0.1),
            row("b", 2, region="forest", satisfaction=0.2),
            row("c", 3, region="forest", satisfaction=0.3),
            row("d", 4, region="forest", satisfaction=0.2),
            row("e", 5, region="forest", satisfaction=0.2),
            row("f", 6, region="forest", satisfaction=0.2),
            row("g", 7, region="forest", satisfaction=0.2),
        ]
        query = {"need": "hunger", "region_id": "forest"}
        baseline, _ = select_related(data, query=query, exclude_key=None, limit=5)
        selected, stats = select_hybrid(data, query=query, exclude_key=None)
        self.assertEqual([x["record_key"] for x in selected[:2]],
                         [x["record_key"] for x in baseline[:2]])
        self.assertEqual(stats["baseline_overlap_counts"], stats["hybrid_overlap_counts"])
        self.assertGreater(stats["hybrid_trajectory_profiles"],
                           stats["baseline_trajectory_profiles"])
        self.assertEqual(stats["anchored_slots"], 2)
        self.assertGreater(stats["diversified_slots"], 0)

    def test_never_crosses_to_partial_when_full_slot_exists(self):
        data = [
            row("a", 1, region="shelter", satisfaction=0.1),
            row("b", 2, region="shelter", satisfaction=0.2),
            row("c", 3, region="forest", satisfaction=0.2),
            row("d", 4, region="forest", satisfaction=0.2),
            row("e", 5, region="forest", satisfaction=0.2),
            row("f", 6, region="forest", satisfaction=0.2),
        ]
        query = {"need": "hunger", "region_id": "forest"}
        selected, stats = select_hybrid(data, query=query, exclude_key=None)
        self.assertEqual(stats["baseline_overlap_counts"], [2, 2, 2, 2, 1])
        self.assertEqual(stats["hybrid_overlap_counts"], [2, 2, 2, 2, 1])
        self.assertEqual(stats["baseline_full_matches"], 4)
        self.assertEqual(stats["hybrid_full_matches"], 4)
        self.assertEqual(len(selected), 5)

    def test_empty_and_excluded_seed_abstain(self):
        selected, stats = select_hybrid(
            [], query={"need": "hunger"}, exclude_key=None,
        )
        self.assertEqual(selected, [])
        self.assertEqual(stats["matching_records"], 0)
        data = [row("a", 1)]
        selected, stats = select_hybrid(
            data, query={"need": "hunger"}, exclude_key="a" * 64,
        )
        self.assertEqual(selected, [])
        self.assertTrue(stats["relevance_vector_preserved"])

    def test_no_alternative_profile_falls_back_without_claims(self):
        data = [row(char, index) for index, char in enumerate("abcdefg", 1)]
        selected, stats = select_hybrid(
            data, query={"need": "hunger"}, exclude_key=None,
        )
        self.assertEqual(stats["baseline_trajectory_profiles"], 1)
        self.assertEqual(stats["hybrid_trajectory_profiles"], 1)
        self.assertEqual(stats["diversified_slots"], 0)
        self.assertEqual(len(selected), 5)

    def test_time_order_seed_exclusion_and_unique_keys(self):
        data = [row(char, index) for index, char in enumerate("abcd", 1)]
        selected, stats = select_hybrid(
            data, query={"need": "hunger"}, exclude_key="d" * 64,
        )
        self.assertEqual(len(selected), 3)
        self.assertNotIn("d" * 64, {x["record_key"] for x in selected})
        self.assertEqual(len({x["record_key"] for x in selected}), 3)
        self.assertEqual(stats["anchored_slots"], 2)

    def test_bad_input_fails_closed(self):
        data = [row("a", 1)]
        for limit, anchors in ((0, 1), (6, 1), (True, 1), (5, 0), (5, 6), (5, True)):
            with self.subTest(limit=limit, anchors=anchors):
                with self.assertRaises(RecallBlocked):
                    select_hybrid(data, query={"need": "hunger"},
                                  exclude_key=None, limit=limit, anchors=anchors)
        with self.assertRaises(RecallBlocked):
            select_hybrid(data, query={}, exclude_key=None)
        with self.assertRaises(RecallBlocked):
            select_hybrid(data + data, query={"need": "hunger"}, exclude_key=None)
        broken = row("b", 3)
        broken["observation"] = {"outcome": {"satisfaction": True}}
        with self.assertRaises(RecallBlocked):
            select_hybrid(data + [broken], query={"need": "hunger"}, exclude_key=None)

    def test_off_by_default_and_no_persistence(self):
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        self.assertNotIn("OwnerHybridRecallWorker", runtime)
        self.assertNotIn("nov_memory_hybrid_shadow", runtime)
        self.assertNotIn("memory_recall_provider=", runtime)
        comparator = (RUNTIME / "nov_memory_hybrid_shadow.py").read_text()
        self.assertNotIn("sqlite3.connect", comparator)
        self.assertNotIn("requests.post", comparator)
        self.assertNotIn("systemctl restart", comparator)
        self.assertTrue(trajectory_signature(row("a", 1)))


if __name__ == "__main__":
    unittest.main()
