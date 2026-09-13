from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from npc_cognitive_stack import NpcCognitiveStack, build_npc_cognitive_stack
from plan_ledger import PlanLedger
from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger
from simulation_clock import SimulationClock
from world_tick import WorldTickRunner
from packages.spatial import (
    AgentIntentResolver,
    DeterministicIntentPlanner,
    FileRegionColdStore,
    Region,
    RegionCatalog,
)


@dataclass(frozen=True)
class AutonomousWorldRuntime:
    """Authoritative single-writer runtime composition without process startup."""

    store: FileRegionColdStore
    engine: ColdAuthoritativeWorldEngine
    regions: RegionCatalog
    guarded_mutations: GuardedMutationService
    proposals: ProposalLedger
    plans: PlanLedger
    planner: DeterministicIntentPlanner
    resolver: AgentIntentResolver
    scheduler: PlanScheduler
    cognition: NpcCognitiveStack
    clock: SimulationClock
    world_tick: WorldTickRunner


def region_catalog_from_world(world: dict[str, Any]) -> RegionCatalog:
    raw_regions = world.get("regions")
    if not isinstance(raw_regions, list) or not raw_regions:
        raise ValueError("authoritative world requires at least one region")

    regions: list[Region] = []
    seen: set[str] = set()
    for raw in raw_regions:
        if not isinstance(raw, dict):
            raise ValueError("region entries must be objects")
        region_id = str(raw.get("id") or "").strip()
        if not region_id:
            raise ValueError("region id is required")
        if region_id in seen:
            raise ValueError(f"duplicate region id: {region_id}")
        seen.add(region_id)

        center = raw.get("center") if isinstance(raw.get("center"), dict) else {}
        try:
            x = float(center["x"])
            y = float(center["y"])
            radius = float(raw["radius"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"region {region_id} requires numeric center x/y and radius") from exc
        if radius <= 0:
            raise ValueError(f"region {region_id} radius must be positive")

        neighbors_raw = raw.get("neighbors")
        if neighbors_raw is None:
            neighbors_raw = []
        if not isinstance(neighbors_raw, list):
            raise ValueError(f"region {region_id} neighbors must be a list")
        neighbors = tuple(sorted({str(v).strip() for v in neighbors_raw if str(v).strip()}))
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        regions.append(Region(
            id=region_id,
            center=(x, y),
            radius=radius,
            biome=str(raw.get("biome") or "unknown"),
            neighbors=neighbors,
            metadata=dict(metadata),
        ))

    known = {region.id for region in regions}
    for region in regions:
        missing = [neighbor for neighbor in region.neighbors if neighbor not in known]
        if missing:
            raise ValueError(f"region {region.id} references unknown neighbors: {','.join(missing)}")
    return RegionCatalog(regions)


def _bootstrap_world(bootstrap_file: Path) -> dict[str, Any]:
    with Path(bootstrap_file).open("r", encoding="utf-8") as fh:
        value = json.load(fh)
    if not isinstance(value, dict):
        raise ValueError("bootstrap world must be an object")
    return value


def build_authoritative_autonomous_runtime(
    *,
    bootstrap_file: Path,
    data_dir: Path,
    cold_store_dir: Path,
    npc_ids: list[str],
    tick_duration_ms: int = 500,
) -> AutonomousWorldRuntime:
    """Compose the deterministic autonomous world graph, but do not start it.

    The function is deliberately side-effect bounded: it initializes persistent
    runtime state under ``data_dir``/``cold_store_dir`` but does not acquire the
    single-writer lease and does not advance logical time. ``run_driver`` remains
    the explicit process-start boundary.
    """

    bootstrap = Path(bootstrap_file)
    if not bootstrap.exists():
        raise FileNotFoundError(f"bootstrap world not found: {bootstrap}")
    root = Path(data_dir)
    cold_root = Path(cold_store_dir)
    root.mkdir(parents=True, exist_ok=True)
    cold_root.mkdir(parents=True, exist_ok=True)

    # Parse topology from bootstrap before the cold engine externalizes entities.
    regions = region_catalog_from_world(_bootstrap_world(bootstrap))
    store = FileRegionColdStore(cold_root)
    engine = ColdAuthoritativeWorldEngine(bootstrap, root, store)
    guarded = GuardedMutationService(engine, decision_log_file=root / "mutation-decisions.jsonl")
    proposals = ProposalLedger(root / "proposals.jsonl")
    plans = PlanLedger(root / "plans.jsonl")
    planner = DeterministicIntentPlanner(store, regions)
    resolver = AgentIntentResolver(store)
    scheduler = PlanScheduler(plans, planner, resolver, guarded, proposal_ledger=proposals)
    world_provider = engine.load_world
    cognition = build_npc_cognitive_stack(
        data_dir=root,
        proposal_ledger=proposals,
        plan_scheduler=scheduler,
        npc_ids=npc_ids,
        world_provider=world_provider,
    )
    clock = SimulationClock(root / "simulation-clock.json", tick_duration_ms=tick_duration_ms)
    world_tick = WorldTickRunner(clock, scheduler, **cognition.world_tick_kwargs())

    return AutonomousWorldRuntime(
        store=store,
        engine=engine,
        regions=regions,
        guarded_mutations=guarded,
        proposals=proposals,
        plans=plans,
        planner=planner,
        resolver=resolver,
        scheduler=scheduler,
        cognition=cognition,
        clock=clock,
        world_tick=world_tick,
    )
