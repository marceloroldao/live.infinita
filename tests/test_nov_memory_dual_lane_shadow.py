"""Supplementary context is separate from, and cannot alter, primary recall."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_dual_lane_shadow import RecallBlocked, select_supplementary
from nov_memory_hybrid_shadow import select_hybrid


def row(label: str, tick: int, *, region: str = "forest",
        need: str = "hunger", satisfaction: float = 0.5):
    return {
        "record_key": label * 64,
        "logical_tick": tick,
        "addresses": {"need": need, "region_id": region, "weather": "sun",
                      "period": "day"},
        "observation": {
            "logical_tick": tick, "need": need,
            "outcome": {"satisfaction": satisfaction, "observed_risk": 0.1,
                        "elapsed_ticks": 3, "preemptions": 0, "replans": 0},
        },
    }


class DualLaneSelectionTests(unittest.TestCase):
    def test_preserves_primary_and_returns_three_partial_alternatives(self) -> None:
        data = [
            row("a", 1, region="shelter", satisfaction=0.1),
            row("b", 2, region="clearing", satisfaction=0.2),
            row("c", 3, region="shelter", satisfaction=0.3),
            row("d", 4),
            row("e", 5),
            row("f", 6),
            row("g", 7),
            row("h", 8),
            row("i", 9),
        ]
        query = {"need": "hunger", "region_id": "forest", "weather": "sun", "period": "day"}
        primary, original = select_hybrid(data, query=query, exclude_key=None)
        old_ids = [record["record_key"] for record in primary]
        additional, counts = select_supplementary(
            data, query=query, exclude_key=None, primary=primary,
        )
        self.assertEqual([record["record_key"] for record in primary], old_ids)
        self.assertEqual(original["hybrid_overlap_counts"], [4] * 5)
        self.assertEqual(counts["supplementary_overlap_counts"], [3, 3, 3])
        self.assertEqual(counts["primary_count_unchanged"], 5)
        self.assertEqual(counts["primary_observed_profiles"], 1)
        self.assertEqual(counts["combined_distinct_observed_profiles"], 4)
        self.assertEqual(counts["supplementary_distinct_observed_profiles"], 3)
        self.assertEqual(set(old_ids) & {record["record_key"] for record in additional}, set())
        self.assertFalse(counts["supplementary_used_to_rank_primary"])
        self.assertFalse(counts["selection_authority"])
        output = json.dumps(counts)
        self.assertNotIn("shelter", output)
        self.assertNotIn("0.1", output)
        self.assertNotIn("record_key", output)

    def test_no_unseen_profile_or_match_abstains(self) -> None:
        data = [row(label, index) for index, label in enumerate("abcde", 1)]
        primary, _ = select_hybrid(
            data, query={"need": "hunger"}, exclude_key=None,
        )
        additional, counts = select_supplementary(
            data, query={"need": "hunger"}, exclude_key=None, primary=primary,
        )
        self.assertEqual(additional, [])
        self.assertEqual(counts["combined_distinct_observed_profiles"], 1)
        other, empty = select_supplementary(
            data, query={"need": "thirst"}, exclude_key=None, primary=[],
        )
        self.assertEqual(other, [])
        self.assertEqual(empty["primary_count_unchanged"], 0)

    def test_excludes_seed_and_profiles_already_primary(self) -> None:
        data = [
            row("a", 1, satisfaction=0.1), row("b", 2, satisfaction=0.2),
            row("c", 3, satisfaction=0.3),
        ]
        primary = [data[1]]
        extras, counts = select_supplementary(
            data, query={"need": "hunger"}, exclude_key="c" * 64, primary=primary,
        )
        self.assertEqual([item["record_key"] for item in extras], ["a" * 64])
        self.assertEqual(counts["combined_distinct_observed_profiles"], 2)

    def test_duplicate_primary_and_invalid_input_block(self) -> None:
        item = row("a", 1)
        with self.assertRaises(RecallBlocked):
            select_supplementary(
                [item], query={"need": "hunger"}, exclude_key=None,
                primary=[item, item],
            )
        for limit in (0, 4, True):
            with self.subTest(limit=limit), self.assertRaises(RecallBlocked):
                select_supplementary(
                    [item], query={"need": "hunger"}, exclude_key=None,
                    primary=[], limit=limit,
                )
        with self.assertRaises(RecallBlocked):
            select_supplementary(
                [item], query={}, exclude_key=None, primary=[],
            )

    def test_off_by_default_with_no_world_writes(self) -> None:
        runtime = (RUNTIME / "autonomous_runtime_main.py").read_text()
        implementation = (RUNTIME / "nov_memory_dual_lane_shadow.py").read_text()
        self.assertNotIn("OwnerDualLaneRecallObserver", runtime)
        self.assertNotIn("nov_memory_dual_lane_shadow", runtime)
        self.assertNotIn("sqlite3.connect", implementation)
        self.assertNotIn("systemctl restart", implementation)


if __name__ == "__main__":
    unittest.main()
