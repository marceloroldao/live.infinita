"""Pure, bounded and privacy-safe MVP-018G diagnostic contracts."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps/world-runtime"
if str(RUNTIME) not in sys.path:
    sys.path.insert(0, str(RUNTIME))

from nov_memory_diagnostics import diversity, retrospective_frame, RecallBlocked


class DiagnosticContracts(unittest.TestCase):
    def test_diversity_counts_only_not_values(self) -> None:
        rows = [
            {"record_key": "a" * 64, "logical_tick": 1,
             "addresses": {"need": "thirst", "region_id": "forest"}},
            {"record_key": "b" * 64, "logical_tick": 2,
             "addresses": {"need": "thirst", "region_id": "forest"}},
            {"record_key": "c" * 64, "logical_tick": 3,
             "addresses": {"need": "hunger", "region_id": "forest"}},
        ]
        result = diversity(rows)
        self.assertEqual(result["distinct_address_values"]["need"], 2)
        self.assertEqual(result["distinct_address_values"]["region_id"], 1)
        self.assertEqual(result["distinct_episode_signatures"], 2)
        self.assertEqual(result["largest_identical_signature_group"], 2)
        self.assertNotIn("thirst", json.dumps(result))
        self.assertNotIn("forest", json.dumps(result))

    def test_empty_context_retrospective_abstains(self) -> None:
        frame = retrospective_frame({"world_id": "w", "sequence": 3}, [])
        self.assertEqual(frame.tick_id, 3)
        self.assertEqual(frame.observer_id, "nov")
        self.assertEqual(frame.state_addresses, ("live:world:w", "live:entity:nov"))
        self.assertEqual(frame.available_interventions, ())
        self.assertEqual(frame.candidate_outcomes, ())

    def test_seed_is_confirmed_not_invented_current_position(self) -> None:
        row = {"record_key": "a" * 64, "logical_tick": 50,
               "addresses": {"need": "hunger", "region_id": "forest"}}
        frame = retrospective_frame({
            "world_id": "w", "sequence": 43,
            "environment": {"period": "day", "weather": "sun"},
        }, [row])
        self.assertEqual(frame.tick_id, 50)
        self.assertIn("live:region:forest", frame.state_addresses)
        self.assertIn("live:period:day", frame.state_addresses)
        self.assertNotIn("live:need:hunger", frame.state_addresses)
        self.assertEqual(frame.provenance["authority"], "read-only-retrospective")

    def test_missing_world_is_rejected(self) -> None:
        with self.assertRaises(RecallBlocked):
            retrospective_frame({"sequence": 1}, [])

    def test_operator_script_stages_only_public_code(self) -> None:
        script = (ROOT / "deploy/mvp018g-nov-memory-diagnostics.sh").read_text()
        self.assertIn('sudo -u liveinfinita env PYTHONPATH="$STAGE:$CORE"', script)
        self.assertIn('chmod 0600 "$LOG"', script)
        self.assertIn('trap cleanup EXIT', script)
        self.assertIn('--samples 20', script)
        self.assertIn("nov_trajectory_recall_shadow", script)
        self.assertNotIn('systemctl restart', script)
        self.assertNotIn('systemctl enable', script)
        self.assertNotIn('MEMORIA_EXTERNAL_EPISODE_PERSISTENCE=bdr', script)


if __name__ == "__main__":
    unittest.main()
