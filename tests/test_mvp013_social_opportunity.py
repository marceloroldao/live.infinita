from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "apps" / "world-runtime"
for p in (str(ROOT), str(RUNTIME)):
    if p not in sys.path:
        sys.path.insert(0, p)

from packages.spatial import FileRegionColdStore, Region, RegionCatalog  # noqa: E402
from npc_social_opportunity import NpcSocialOpportunity  # noqa: E402
from npc_audited_reordering_need_scheduler import NpcAuditedReorderingNeedScheduler  # noqa: E402
from cognitive_contextual import freeze_contextual_forecast  # noqa: E402
from npc_need_dynamics import NpcNeedDynamics  # noqa: E402
from npc_need_outcomes import NpcNeedOutcomeProcessor  # noqa: E402
from npc_composite_strategy_outcomes import NpcCompositeStrategyOutcomeProcessor  # noqa: E402
from npc_strategy_experience import NpcStrategyExperience  # noqa: E402
from tests.test_npc_need_scheduler import (  # noqa: E402
    FakeProposalLedger, FakePlanScheduler, FakeCompositeProvider,
    FakeStrategyExecutor as FakeCompositeExecutor,
)
from npc_strategy_compiler import NpcStrategyCompiler  # noqa: E402
from tests.test_npc_composite_strategy_outcomes import FakeStrategyExecutor, FakePlanLedger, FakeNeedOutcomes  # noqa: E402


def actor(name, region="clearing", *, available=True, capabilities=True, x=10):
    return {
        "id": name, "type": "agent", "region_id": region,
        "position": {"x": x, "y": 0},
        "properties": {
            "interaction_capabilities": ["social"] if capabilities else [],
            "available_for_interaction": available,
        },
    }


def nov():
    return {
        "id": "nov", "type": "human", "region_id": "clearing",
        "position": {"x": 0, "y": 0},
        "properties": {
            "needs": {"social": 0.9, "curiosity": 0.0, "safety": 0.0, "energy": 0.0},
        },
    }


class Needs:
    def get_needs(self, npc_id):
        return {"social": 1.0, "curiosity": 0.0, "safety": 0.0, "energy": 0.0}


class SocialOpportunityTests(unittest.TestCase):
    def setup_world(self, root, entities):
        store = FileRegionColdStore(root / "cold-store")
        store.replace_all(entities)
        catalog = RegionCatalog([
            Region(id="clearing", center=(0, 0), radius=100, neighbors=("forest",)),
            Region(id="forest", center=(100, 0), radius=100, neighbors=("clearing", "far")),
            Region(id="far", center=(200, 0), radius=100, neighbors=("forest",)),
        ])
        return store, NpcSocialOpportunity(store, catalog, max_candidates=2)

    def test_no_actor_does_not_invent_a_social_target(self):
        with tempfile.TemporaryDirectory() as d:
            store, provider = self.setup_world(Path(d), [nov()])
            info = provider.discover(store.get_entity("nov"))
            self.assertEqual(info["status"], "no_observed_social_actor")
            self.assertEqual(info["candidate_ids"], [])
            self.assertEqual(info["region_ids"], ["clearing", "forest"])
            self.assertFalse(info["mutates_world"])
            forecast, _ = freeze_contextual_forecast(
                frame_id="f", world_version=1, world_sequence=2,
                observer=store.get_entity("nov"), needs=Needs().get_needs("nov"),
                target_provider=store.get_entity, social_opportunity_provider=provider,
            )
            self.assertEqual(forecast["reason"], "no_configured_target")
            self.assertEqual(forecast["social_opportunity"]["candidate_ids"], [])

    def test_actual_available_entity_in_neighbor_is_discovered_not_type_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            entities = [nov(), actor("a", "forest"), actor("b", "forest", available=False),
                        actor("c", "clearing", capabilities=False),
                        actor("nov", "forest"), actor("far_actor", "far"),
                        actor("z", "clearing", x=float("nan"))]
            # One ID per cold store: the observer itself may not be duplicated.
            entities = [e for e in entities if not (e["id"]=="nov" and e["region_id"]=="forest")]
            store, provider = self.setup_world(Path(d), entities)
            info = provider.discover(store.get_entity("nov"))
            self.assertEqual(info["candidate_ids"], ["a"])
            self.assertEqual(info["status"], "observed")
            self.assertEqual(info["evidence"][0]["source"], "entity_properties")
            info["candidate_ids"].append("fake")
            self.assertEqual(provider.candidates(store.get_entity("nov")), ["a"])
            self.assertNotIn("social_target_entity_id", store.get_entity("nov")["properties"])

    def test_deterministic_bounded_candidates_revalidates_availability(self):
        with tempfile.TemporaryDirectory() as d:
            store, provider = self.setup_world(Path(d), [
                nov(), actor("z"), actor("b"), actor("a"),
            ])
            self.assertEqual(provider.candidates(store.get_entity("nov")), ["a","b"])
            target = store.get_entity("a")
            target["properties"]["available_for_interaction"] = False
            store.upsert(target)
            self.assertEqual(provider.candidates(store.get_entity("nov")), ["b","z"])

    def test_scheduler_uses_real_social_candidate_without_configured_target(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store, provider = self.setup_world(root, [nov(), actor("friend")])
            proposals = FakeProposalLedger()
            plans = FakePlanScheduler(store)
            scheduler = NpcAuditedReorderingNeedScheduler(
                root / "needs.jsonl", proposals, plans, npc_ids=["nov"],
                need_state_provider=Needs(), social_opportunity_provider=provider,
            )
            rows = scheduler.evaluate_tick(1)
            self.assertEqual(len(rows), 1)
            row = rows[0]
            self.assertEqual(row["status"], "scheduled")
            self.assertEqual(row["need"], "social")
            self.assertEqual(row["selected_target_entity_id"], "friend")
            self.assertEqual(row["target_evidence_source"], "observed_social_capability")
            self.assertEqual(row["skipped_unresolved_needs"], [])
            self.assertEqual(plans.calls[0]["intent"]["target_evidence_source"], "observed_social_capability")
            self.assertEqual(proposals.calls[0][1]["metadata"]["target_evidence_source"], "observed_social_capability")
            self.assertNotIn("social_target_entity_id", store.get_entity("nov")["properties"])
            forecast, target = freeze_contextual_forecast(
                frame_id="f", world_version=1, world_sequence=2,
                observer=store.get_entity("nov"), needs=Needs().get_needs("nov"),
                target_provider=store.get_entity, social_opportunity_provider=provider,
            )
            self.assertEqual(forecast["status"], "issued")
            self.assertEqual(forecast["target_entity_id"], "friend")
            self.assertEqual(forecast["target_evidence_source"], "observed_social_capability")
            self.assertFalse(forecast["predicts_action"])
            self.assertIsNotNone(target)

    def test_composite_terminal_phase_retains_social_provenance(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            store, provider = self.setup_world(root, [nov(), actor("friend")])
            proposals = FakeProposalLedger()
            plans = FakePlanScheduler(store)
            executor = FakeCompositeExecutor()
            scheduler = NpcAuditedReorderingNeedScheduler(
                root / "needs.jsonl", proposals, plans, npc_ids=["nov"],
                need_state_provider=Needs(), social_opportunity_provider=provider,
                composite_strategy_provider=FakeCompositeProvider(),
                strategy_compiler=NpcStrategyCompiler(), strategy_executor=executor,
            )
            result = scheduler.evaluate_tick(1)[0]
            self.assertEqual(result["status"], "scheduled")
            self.assertEqual(result["target_evidence_source"], "observed_social_capability")
            phases = executor.calls[0]["strategy_plan"]["phases"]
            self.assertFalse(phases[0]["intent"]["need_outcome_eligible"])
            self.assertEqual(phases[-1]["intent"]["target_entity_id"], "friend")
            self.assertEqual(phases[-1]["intent"]["target_evidence_source"],
                             "observed_social_capability")

    def test_two_social_candidates_force_contextual_abstention_without_rank(self):
        with tempfile.TemporaryDirectory() as d:
            store, provider = self.setup_world(Path(d), [nov(), actor("a"), actor("b")])
            forecast, target = freeze_contextual_forecast(
                frame_id="f", world_version=1, world_sequence=2,
                observer=store.get_entity("nov"), needs=Needs().get_needs("nov"),
                target_provider=store.get_entity, social_opportunity_provider=provider,
            )
            self.assertEqual(forecast["reason"], "multiple_targets_without_ranked_evidence")
            self.assertIsNone(target)


if __name__ == "__main__":
    unittest.main()
