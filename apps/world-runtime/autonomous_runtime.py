from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cold_engine import ColdAuthoritativeWorldEngine
from conditional_event_scheduler import ConditionalEventScheduler
from mutation_gate_service import GuardedMutationService
from npc_cognitive_stack import NpcCognitiveStack, build_npc_cognitive_stack
from plan_ledger import PlanLedger
from plan_scheduler import PlanScheduler
from proposal_ledger import ProposalLedger
from simulation_clock import SimulationClock
from world_event_scheduler import WorldEventScheduler
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
    event_scheduler: WorldEventScheduler
    conditional_event_scheduler: ConditionalEventScheduler
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


def _simulation_block(bootstrap_world: dict[str, Any]) -> dict[str, Any]:
    simulation = bootstrap_world.get("simulation")
    if simulation is None:
        return {}
    if not isinstance(simulation, dict):
        raise ValueError("simulation must be an object")
    return simulation


def _install_bootstrap_schedules(
    bootstrap_world: dict[str, Any],
    event_scheduler: WorldEventScheduler,
) -> None:
    simulation = _simulation_block(bootstrap_world)
    raw_events = simulation.get("scheduled_events", [])
    if not isinstance(raw_events, list):
        raise ValueError("simulation.scheduled_events must be a list")

    world_id = str(bootstrap_world.get("world_id") or "world").strip() or "world"
    seen_ids: set[str] = set()
    principal = {
        "source": "world_schedule",
        "actor_id": "world",
        "authority": "system",
        "subject_entity_id": None,
    }
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise ValueError("scheduled event entries must be objects")
        schedule_id = str(raw.get("id") or "").strip()
        if not schedule_id:
            raise ValueError("scheduled event id is required")
        if schedule_id in seen_ids:
            raise ValueError(f"duplicate scheduled event id: {schedule_id}")
        seen_ids.add(schedule_id)
        try:
            due_tick = int(raw["due_tick"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"scheduled event {schedule_id} requires integer due_tick") from exc
        operations = raw.get("operations")
        if not isinstance(operations, list) or not operations or not all(isinstance(row, dict) for row in operations):
            raise ValueError(f"scheduled event {schedule_id} requires non-empty operations")
        recurrence_raw = raw.get("recurrence_every_ticks")
        recurrence = None
        if recurrence_raw is not None:
            try:
                recurrence = int(recurrence_raw)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"scheduled event {schedule_id} recurrence must be an integer") from exc
        event_scheduler.schedule(
            due_tick=due_tick,
            operations=operations,
            principal=principal,
            narration=str(raw.get("narration") or ""),
            recurrence_every_ticks=recurrence,
            metadata={
                "bootstrap_world_id": world_id,
                "bootstrap_schedule_id": schedule_id,
            },
            idempotency_key=f"bootstrap-world-event:{world_id}:{schedule_id}",
        )


def _install_bootstrap_conditionals(
    bootstrap_world: dict[str, Any],
    conditional_scheduler: ConditionalEventScheduler,
) -> None:
    simulation = _simulation_block(bootstrap_world)
    raw_events = simulation.get("conditional_events", [])
    if not isinstance(raw_events, list):
        raise ValueError("simulation.conditional_events must be a list")

    world_id = str(bootstrap_world.get("world_id") or "world").strip() or "world"
    principal = {
        "source": "world_condition",
        "actor_id": "world",
        "authority": "system",
        "subject_entity_id": None,
    }
    seen_ids: set[str] = set()
    for raw in raw_events:
        if not isinstance(raw, dict):
            raise ValueError("conditional event entries must be objects")
        event_id = str(raw.get("id") or "").strip()
        if not event_id:
            raise ValueError("conditional event id is required")
        if event_id in seen_ids:
            raise ValueError(f"duplicate conditional event id: {event_id}")
        seen_ids.add(event_id)
        condition = raw.get("condition")
        operations = raw.get("operations")
        if not isinstance(condition, dict):
            raise ValueError(f"conditional event {event_id} requires condition")
        if not isinstance(operations, list) or not operations or not all(isinstance(row, dict) for row in operations):
            raise ValueError(f"conditional event {event_id} requires non-empty operations")
        try:
            cooldown_ticks = int(raw.get("cooldown_ticks", 0))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"conditional event {event_id} cooldown_ticks must be an integer") from exc
        conditional_scheduler.register(
            condition=condition,
            principal=principal,
            operations=operations,
            trigger_mode=str(raw.get("trigger_mode") or "edge"),
            cooldown_ticks=cooldown_ticks,
            one_shot=bool(raw.get("one_shot", False)),
            narration=str(raw.get("narration") or ""),
            metadata={
                "bootstrap_world_id": world_id,
                "bootstrap_conditional_id": event_id,
            },
            idempotency_key=f"bootstrap-conditional-event:{world_id}:{event_id}",
        )


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

    bootstrap_value = _bootstrap_world(bootstrap)
    regions = region_catalog_from_world(bootstrap_value)
    store = FileRegionColdStore(cold_root)
    engine = ColdAuthoritativeWorldEngine(bootstrap, root, store)
    guarded = GuardedMutationService(engine, decision_log_file=root / "mutation-decisions.jsonl")
    proposals = ProposalLedger(root / "proposals.jsonl")
    plans = PlanLedger(root / "plans.jsonl")
    planner = DeterministicIntentPlanner(store, regions)
    # The persistent map may grow after startup through collective intent. Every
    # plan/revalidation refreshes topology from current authoritative world.json.
    planner.set_world_provider(engine.load_world)
    resolver = AgentIntentResolver(store)
    scheduler = PlanScheduler(plans, planner, resolver, guarded, proposal_ledger=proposals)
    event_scheduler = WorldEventScheduler(root / "world-event-schedule.jsonl", guarded)
    conditional_event_scheduler = ConditionalEventScheduler(root / "conditional-world-events.jsonl", guarded)
    # One-time compatibility migration for files affected by the historical
    # truncated-tail-then-append bug. The scheduler preserves a full backup and
    # quarantines the invalid bytes; subsequent mid-log corruption stays fatal.
    conditional_event_scheduler.repair_legacy_single_invalid_record()
    _install_bootstrap_schedules(bootstrap_value, event_scheduler)
    _install_bootstrap_conditionals(bootstrap_value, conditional_event_scheduler)
    world_provider = engine.load_world
    cognition = build_npc_cognitive_stack(
        data_dir=root,
        proposal_ledger=proposals,
        plan_scheduler=scheduler,
        npc_ids=npc_ids,
        world_provider=world_provider,
    )
    clock = SimulationClock(root / "simulation-clock.json", tick_duration_ms=tick_duration_ms)
    world_tick = WorldTickRunner(
        clock,
        scheduler,
        event_scheduler=event_scheduler,
        conditional_event_scheduler=conditional_event_scheduler,
        **cognition.world_tick_kwargs(),
    )

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
        event_scheduler=event_scheduler,
        conditional_event_scheduler=conditional_event_scheduler,
        cognition=cognition,
        clock=clock,
        world_tick=world_tick,
    )
