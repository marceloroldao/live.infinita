import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for value in (str(ROOT), str(RUNTIME)):
    if value not in sys.path:
        sys.path.insert(0, value)

from npc_causal_forecast import NpcCausalForecast
from npc_causal_model import NpcCausalModel
from npc_composite_strategy import NpcCompositeStrategy


class FakeStore:
    def __init__(self):
        self.rows = {
            "npc": {"id": "npc", "region_id": "r0", "properties": {}},
            "goal": {"id": "goal", "region_id": "r2", "properties": {"risk_level": 0.20}},
            "shelter": {"id": "shelter", "region_id": "r1", "properties": {"risk_level": 0.02}},
        }

    def get_entity(self, entity_id):
        return self.rows.get(entity_id)


class FakeRegions:
    ROUTES = {
        ("r0", "r2"): ["r0", "r2"],
        ("r0", "r1"): ["r0", "r1"],
        ("r1", "r2"): ["r1", "r2"],
    }

    def route(self, source, goal):
        return list(self.ROUTES.get((source, goal), []))


class FakePlanner:
    def __init__(self):
        self.store = FakeStore()
        self.regions = FakeRegions()


class FakeForecast:
    def assess(self, *, context, estimated_ticks):
        if estimated_ticks <= 0:
            return None
        return {
            "forecast_schema": "npc_causal_forecast_v1",
            "current_danger": 0.10,
            "projected_danger": 0.70,
            "blend": 0.50,
            "confidence": 0.80,
            "ticks_until": 1,
            "estimated_ticks": estimated_ticks,
        }


class MatureExperience:
    def strategy_stats(self, npc_id, need, target_id, strategy_id, context):
        return {
            "empirical_ready": True,
            "mean_satisfaction": 0.60,
            "mean_elapsed_ticks": 2.0,
            "mean_observed_risk": 0.30,
            "mean_preemptions": 0.0,
            "mean_replans": 0.0,
        }


class NpcCausalForecastTest(unittest.TestCase):
    def _schedule(self, path: Path, due_tick: int = 12):
        row = {
            "scheduled_event_id": "night",
            "status": "scheduled",
            "due_tick": due_tick,
            "operations": [
                {"op": "set_world", "path": ["environment", "period"], "value": "night"},
                {"op": "set_world", "path": ["environment", "danger_level"], "value": 0.35},
            ],
            "metadata": {"bootstrap_schedule_id": "night-cycle"},
        }
        path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    def _learn_night_risk(self, model: NpcCausalModel):
        for index, tick in enumerate((12, 36, 60), start=1):
            model.observe_environment_transition(
                observation_id=f"night-{index}",
                logical_tick=tick,
                before={"period": "day", "weather": "clear", "danger_level": 0.05},
                after={"period": "night", "weather": "clear", "danger_level": 0.35},
                source_events=[{"scheduled_event_id": "night"}],
            )

    def test_forecast_only_applies_when_strategy_crosses_scheduled_transition(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            schedule = root / "world-event-schedule.jsonl"
            self._schedule(schedule, due_tick=12)
            model = NpcCausalModel(root / "causal.json")
            self._learn_night_risk(model)
            forecast = NpcCausalForecast(model, schedule)
            context = {"logical_tick": 10, "period": "day", "weather": "clear", "danger_level": 0.05}

            self.assertIsNone(forecast.assess(context=context, estimated_ticks=1))
            result = forecast.assess(context=context, estimated_ticks=2)
            self.assertIsNotNone(result)
            self.assertEqual(result["to_period"], "night")
            self.assertEqual(result["ticks_until"], 2)
            self.assertGreater(result["projected_danger"], result["current_danger"])
            self.assertGreater(result["confidence"], 0.0)

    def test_composite_strategy_uses_smaller_future_risk_exposure_via_shelter(self):
        planner = FakePlanner()
        strategy = NpcCompositeStrategy(planner, causal_forecast_provider=FakeForecast())
        rows = strategy.candidates(
            actor_entity_id="npc",
            target_entity_id="goal",
            predicted_satisfaction=0.8,
            context={"logical_tick": 11, "period": "day", "danger_level": 0.10},
            shelter_entity_ids=["shelter"],
            wait_ticks=0,
        )
        ranked = strategy.rank(
            rows,
            actor_entity_id="npc",
            need="curiosity",
            target_entity_id="goal",
            context={"logical_tick": 11, "period": "day", "danger_level": 0.10},
            travel_weight=0.0,
            risk_weight=1.0,
        )
        by_id = {row["strategy_id"]: row for row in ranked}
        direct = by_id["direct"]
        sheltered = by_id["via_shelter:shelter"]
        self.assertEqual(direct["cost_source"], "heuristic+causal_forecast")
        self.assertEqual(sheltered["cost_source"], "heuristic+causal_forecast")
        self.assertEqual(direct["causal_forecast_exposure"], 1.0)
        self.assertEqual(sheltered["causal_forecast_exposure"], 0.5)
        self.assertGreater(direct["effective_risk"], sheltered["effective_risk"])
        self.assertEqual(ranked[0]["strategy_id"], "via_shelter:shelter")

    def test_empirical_strategy_evidence_disables_causal_prior(self):
        planner = FakePlanner()
        strategy = NpcCompositeStrategy(
            planner,
            strategy_experience_provider=MatureExperience(),
            causal_forecast_provider=FakeForecast(),
        )
        rows = strategy.candidates(
            actor_entity_id="npc",
            target_entity_id="goal",
            predicted_satisfaction=0.8,
            context={"logical_tick": 11, "period": "day", "danger_level": 0.10},
            shelter_entity_ids=["shelter"],
            wait_ticks=0,
        )
        ranked = strategy.rank(
            rows,
            actor_entity_id="npc",
            need="curiosity",
            target_entity_id="goal",
            context={"logical_tick": 11, "period": "day", "danger_level": 0.10},
        )
        self.assertTrue(ranked)
        for row in ranked:
            self.assertEqual(row["cost_source"], "empirical")
            self.assertIsNone(row["causal_forecast"])
            self.assertEqual(row["causal_forecast_exposure"], 0.0)


if __name__ == "__main__":
    unittest.main()
