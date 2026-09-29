"""Observed trajectory diversity and comparison, never authoritative action."""
from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_recall_shadow import RecallBlocked
from nov_trajectory_recall_shadow import (
    address_signature, outcome_signature, compare_trajectory_recall,
    trajectory_distribution,
)


def observation(letter: str, tick: int, *, need: str = "curiosity",
                region: str = "forest", satisfaction: float = 0.4):
    return {
        "record_key": letter * 64,
        "logical_tick": tick,
        "addresses": {
            "need": need, "region_id": region, "period": "day",
            "weather": "sun", "target_entity_id": "ancient_tree", "strategy_id": "explore",
        },
        "observation": {
            "logical_tick": tick, "need": need,
            "context": {"region_id": region, "period": "day", "weather": "sun"},
            "outcome": {
                "satisfaction": satisfaction, "observed_risk": 0.1,
                "elapsed_ticks": 10, "preemptions": 0, "replans": 0,
            },
        },
    }


class TrajectoryComparatorTests(unittest.TestCase):
    def test_diversifies_observed_outcome_without_inventing_evidence(self) -> None:
        rows = [
            observation("a", 1, satisfaction=0.9),
            observation("b", 2, satisfaction=0.4),
            observation("c", 3, satisfaction=0.4),
            observation("d", 4, satisfaction=0.4),
            observation("e", 5, satisfaction=0.4),
            observation("f", 6, satisfaction=0.4),
        ]
        query = {"need": "curiosity", "region_id": "forest"}
        result = compare_trajectory_recall(
            rows, query=query, exclude_key=None, limit=3,
        )
        self.assertEqual(result["matching_records"], 6)
        self.assertEqual(result["candidate_address_profiles"], 1)
        self.assertEqual(result["candidate_outcome_profiles"], 2)
        self.assertEqual(result["baseline"]["unique_observed_trajectory_profiles"], 1)
        self.assertEqual(result["diversified"]["unique_observed_trajectory_profiles"], 2)
        self.assertEqual(result["baseline"]["overlap_counts"], [2, 2, 2])
        self.assertEqual(result["diversified"]["overlap_counts"], [2, 2, 2])
        self.assertEqual(result["diversified"]["retrieved_count"], 3)
        self.assertFalse(result["selection_authority"])
        self.assertFalse(result["new_evidence_created"])
        self.assertFalse(result["causal_inference_claim"])
        summary = json.dumps(result)
        self.assertNotIn("curiosity", summary)
        self.assertNotIn("0.9", summary)
        self.assertNotIn("record_key", summary)

    def test_preserves_query_relevance_and_shows_partial_matches(self) -> None:
        rows = [
            observation("a", 1, region="forest"),
            observation("b", 2, region="forest"),
            observation("c", 3, region="shelter", satisfaction=0.3),
        ]
        query = {"need": "curiosity", "region_id": "forest"}
        result = compare_trajectory_recall(
            rows, query=query, exclude_key=None, limit=2,
        )
        self.assertEqual(result["matching_records"], 3)
        self.assertEqual(result["baseline"]["full_address_matches"], 2)
        self.assertEqual(result["diversified"]["full_address_matches"], 1)
        self.assertEqual(result["diversified"]["partial_address_matches"], 1)
        self.assertEqual(result["diversified"]["overlap_counts"], [2, 1])

    def test_excludes_seed_and_does_not_fabricate_from_no_matches(self) -> None:
        rows = [observation("a", 1)]
        matches = compare_trajectory_recall(
            rows, query={"need": "curiosity"},
            exclude_key="a" * 64, limit=5,
        )
        self.assertEqual(matches["matching_records"], 0)
        self.assertEqual(matches["diversified"]["retrieved_count"], 0)

    def test_sequence_counts_are_directed_and_descriptive(self) -> None:
        rows = [
            observation("a", 1, region="forest"),
            observation("b", 2, region="forest"),
            observation("c", 3, region="shelter"),
            observation("d", 4, region="forest"),
        ]
        summary = trajectory_distribution(rows[::-1])
        self.assertEqual(summary["observed_address_transitions"], 3)
        self.assertEqual(summary["self_address_transitions"], 1)
        self.assertEqual(summary["distinct_directed_address_transitions"], 3)
        self.assertEqual(summary["unique_observed_trajectory_profiles"], 2)
        self.assertEqual(summary["largest_identical_trajectory_profile_group"], 3)

    def test_none_outcome_is_observed_absence_not_invented_value(self) -> None:
        row = observation("a", 1)
        row["observation"]["outcome"] = {"satisfaction": None}
        self.assertEqual(len(outcome_signature(row)), 5)
        self.assertTrue(all(value is None for _, value in outcome_signature(row)))
        self.assertEqual(len(address_signature(row)), 6)
        self.assertEqual(trajectory_distribution([])["observed_address_transitions"], 0)

    def test_invalid_outcomes_and_queries_fail_closed(self) -> None:
        row = observation("a", 1)
        for value in (True, math.nan, -1.0, "high"):
            with self.subTest(value=str(value)):
                broken = dict(row)
                broken["observation"] = dict(row["observation"])
                broken["observation"]["outcome"] = {"satisfaction": value}
                with self.assertRaises(RecallBlocked):
                    trajectory_distribution([broken])
        with self.assertRaises(RecallBlocked):
            compare_trajectory_recall([row], query={}, exclude_key=None, limit=5)
        with self.assertRaises(RecallBlocked):
            compare_trajectory_recall([row], query={"need": "curiosity"}, exclude_key=None, limit=9)


if __name__ == "__main__":
    unittest.main()
