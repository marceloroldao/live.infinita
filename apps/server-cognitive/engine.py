from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass, is_dataclass
from threading import RLock
from typing import Any

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
)
from memoria_resolutiva.structural_temporal_observation_v2 import (
    StructuralTemporalObservationMemory,
)
from reality_slice import RealitySliceReorderBuffer, TemporalAssociator

from closed_loop_runtime import execute_validated_action
from context_observation_memoria_adapter import (
    ingest_higher_order_context_candidate,
    refresh_higher_order_context_resolution_state,
)
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from higher_order_context_selector import (
    make_sparse_context_associator,
    policy_from_world as higher_order_policy_from_world,
    resolve_higher_order_context_states,
    select_higher_order_context_candidates,
)
from nov_autonomous_life import (
    choose_autonomous_action,
    needs_after_committed_action,
)
from reality_slice_bridge import reality_window_from_world_rule
from reality_slice_event_time_runtime import (
    flush_reality_slice_event_time,
    ingest_reality_slice_event_time,
)
from scenario_server_cognitive_rc1 import (
    build_server_cognitive_rc1_world,
    initial_server_cognitive_rc1_needs,
)
from temporal_evidence_selector import (
    admitted_candidates,
    policy_from_world as temporal_policy_from_world,
    select_temporal_evidence_candidates,
)
from temporal_observation_memoria_adapter import ingest_temporal_evidence_candidate


@dataclass(frozen=True, slots=True)
class ServerCycleResult:
    cycle_id: int
    world_tick: int
    world_version: int
    reality_slice_id: int
    emitted_slice_ids: tuple[int, ...]
    rejected_slice_ids: tuple[int, ...]
    nov_mode: str
    nov_action: str
    nov_consequence: str
    temporal_candidates: int
    higher_order_candidates: int
    resolved_contexts: int
    ambiguous_contexts: int
    unsupported_contexts: int


class ServerCognitiveEngine:
    """Long-running deterministic cognitive engine for Server Cognitive RC1.

    World Runtime remains authoritative. bit.analyze receives only RealitySlices.
    Memoria.ia stores structural observations/current admission, while the situated
    causal gym drives Nov's autonomous curiosity/need action loop.
    """

    def __init__(
        self,
        *,
        episode_id: int = 1,
        observer_id: str = "nova",
        activity_limit: int = 500,
    ) -> None:
        self.lock = RLock()
        self.observer_id = str(observer_id)
        self.world = build_server_cognitive_rc1_world(episode_id=episode_id)
        self.needs = initial_server_cognitive_rc1_needs(self.world)

        self.gym = SituatedLiveCognitiveGymV2(
            min_independent_episodes=2,
            min_contiguous_support=2,
        )
        self.pairwise = TemporalAssociator(lambda0=0.0)
        self.higher_policy = higher_order_policy_from_world(self.world)
        self.higher = make_sparse_context_associator(self.higher_policy)

        event_time_rule = (
            (self.world.get("rules") or {}).get("reality_slice_event_time") or {}
        )
        self.reorder = RealitySliceReorderBuffer(
            allowed_lateness=float(event_time_rule.get("allowed_lateness", 1.0))
        )

        self.temporal_memory = StructuralTemporalObservationMemory()
        self.context_memory = StructuralContextObservationMemory()
        self.admission_memory = StructuralContextAdmissionStateMemory()

        self.provenance_by_slice: dict[int, tuple[str, ...]] = {}
        self.activity: deque[dict[str, Any]] = deque(maxlen=int(activity_limit))
        self.rejections: deque[dict[str, Any]] = deque(maxlen=int(activity_limit))

        self.cycle_id = 0
        self.simulation_time = 0.0
        self.last_decision: dict[str, Any] | None = None
        self.last_causal_step: Any | None = None

    @staticmethod
    def _actual_candidate_id(request: Any, consequence_address: str) -> str:
        consequence = (str(consequence_address),)
        return next(
            candidate.candidate_id
            for candidate in request.candidates
            if candidate.consequence_addresses == consequence
        )

    @staticmethod
    def _jsonable(value: Any) -> Any:
        if is_dataclass(value):
            return {
                key: ServerCognitiveEngine._jsonable(item)
                for key, item in asdict(value).items()
            }
        if isinstance(value, dict):
            return {
                str(key): ServerCognitiveEngine._jsonable(item)
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list, set, frozenset, deque)):
            return [ServerCognitiveEngine._jsonable(item) for item in value]
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        return repr(value)

    def _environment_window(self):
        config = (self.world.get("rules") or {}).get("server_cognitive_rc1") or {}
        frame_count = int(config.get("sensor_frames_per_cycle", 3))
        env_ticks = int(config.get("environment_ticks_between_frames", 1))
        if frame_count < 2:
            raise ValueError("sensor_frames_per_cycle must be >= 2")
        if env_ticks < 1:
            raise ValueError("environment_ticks_between_frames must be >= 1")

        for index in range(frame_count):
            sampled = sample_multimodal_sensor_frame(
                self.world,
                observer_id=self.observer_id,
            )
            self.world = sampled.world
            if index + 1 < frame_count:
                for _ in range(env_ticks):
                    self.world = advance_distributed_environmental_agents(
                        self.world,
                        ticks=1,
                    )[0].world

        window = reality_window_from_world_rule(
            self.world,
            observer_id=self.observer_id,
            time_origin=self.simulation_time,
        )
        step = float(config.get("simulation_time_step", 1.0))
        if step <= 0:
            raise ValueError("simulation_time_step must be > 0")
        self.simulation_time += step
        return window

    def _ingest_window(self, window) -> tuple[tuple[int, ...], tuple[int, ...]]:
        reality_slice = window.reality_slice
        self.provenance_by_slice[int(reality_slice.slice_id)] = tuple(window.frame_ids)

        result = ingest_reality_slice_event_time(
            self.reorder,
            self.pairwise,
            self.higher,
            reality_slice,
        )
        rejected_ids: list[int] = []
        for rejection in result.batch.rejected:
            payload = self._jsonable(rejection)
            self.rejections.append(payload)
            rejected_ids.append(int(rejection.slice_id))
        return result.ingested_slice_ids, tuple(rejected_ids)

    def _refresh_structural_memory(self, supporting_slice_ids: tuple[int, ...]):
        temporal_decisions = select_temporal_evidence_candidates(
            self.pairwise,
            temporal_policy_from_world(self.world),
            provenance_by_slice=self.provenance_by_slice,
        )
        temporal = admitted_candidates(temporal_decisions)
        for candidate in temporal:
            ingest_temporal_evidence_candidate(
                self.temporal_memory,
                candidate,
                provenance="live.infinita/server-cognitive-rc1",
            )

        higher_candidates = select_higher_order_context_candidates(
            self.pairwise,
            self.higher,
            self.higher_policy,
            provenance_by_slice=self.provenance_by_slice,
        )
        for candidate in higher_candidates:
            ingest_higher_order_context_candidate(
                self.context_memory,
                candidate,
            )

        resolutions = resolve_higher_order_context_states(
            self.pairwise,
            self.higher,
            self.higher_policy,
        )
        refresh_higher_order_context_resolution_state(
            self.admission_memory,
            resolutions,
            source_epoch_id=f"server-cycle-{self.cycle_id}",
            supporting_slice_ids=supporting_slice_ids,
        )
        return temporal, higher_candidates, resolutions

    def _nov_cycle(self):
        decision = choose_autonomous_action(
            gym=self.gym,
            world=self.world,
            needs=self.needs,
            observer_id=self.observer_id,
        )
        execution = execute_validated_action(
            self.world,
            decision.proposal,
        )
        actual_id = self._actual_candidate_id(
            decision.request,
            execution.consequence_address,
        )
        causal_step = self.gym.step(
            decision.request,
            actual_candidate_id=actual_id,
            learn=True,
        )
        self.needs = needs_after_committed_action(
            decision=decision,
            result_tick=int(execution.world["current_tick"]),
        )
        self.world = execution.world
        self.last_decision = {
            "mode": decision.mode,
            "action": decision.proposal["action"],
            "proposal_id": decision.proposal["proposal_id"],
            "target": decision.proposal.get("target"),
            "consequence": execution.consequence_address,
        }
        self.last_causal_step = causal_step
        return decision, execution, causal_step

    def step(self) -> ServerCycleResult:
        with self.lock:
            self.cycle_id += 1
            window = self._environment_window()
            emitted, rejected = self._ingest_window(window)
            temporal, higher, resolutions = self._refresh_structural_memory(emitted)
            decision, execution, _causal_step = self._nov_cycle()

            counts = {"resolved": 0, "ambiguous": 0, "unsupported": 0}
            for item in resolutions:
                counts[item.resolution_state] = counts.get(item.resolution_state, 0) + 1

            result = ServerCycleResult(
                cycle_id=self.cycle_id,
                world_tick=int(self.world["current_tick"]),
                world_version=int(self.world["current_version"]),
                reality_slice_id=int(window.reality_slice.slice_id),
                emitted_slice_ids=tuple(int(value) for value in emitted),
                rejected_slice_ids=tuple(int(value) for value in rejected),
                nov_mode=decision.mode,
                nov_action=str(decision.proposal["action"]),
                nov_consequence=str(execution.consequence_address),
                temporal_candidates=len(temporal),
                higher_order_candidates=len(higher),
                resolved_contexts=counts["resolved"],
                ambiguous_contexts=counts["ambiguous"],
                unsupported_contexts=counts["unsupported"],
            )
            self.activity.append(
                {
                    "kind": "cycle",
                    **self._jsonable(result),
                }
            )
            return result

    def run_steps(self, count: int) -> tuple[ServerCycleResult, ...]:
        count = int(count)
        if count < 1 or count > 1000:
            raise ValueError("count must be between 1 and 1000")
        return tuple(self.step() for _ in range(count))

    def save_checkpoint(self, path: str):
        from checkpoint import save_engine_checkpoint
        with self.lock:
            return save_engine_checkpoint(self, path)

    @classmethod
    def load_checkpoint(cls, path: str):
        from checkpoint import load_engine_checkpoint
        engine = load_engine_checkpoint(path)
        if not isinstance(engine, cls):
            raise TypeError("checkpoint did not restore ServerCognitiveEngine")
        return engine

    def flush_event_time(self) -> tuple[int, ...]:
        with self.lock:
            result = flush_reality_slice_event_time(
                self.reorder,
                self.pairwise,
                self.higher,
            )
            if result.ingested_slice_ids:
                self._refresh_structural_memory(result.ingested_slice_ids)
            return result.ingested_slice_ids

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            nova = ((self.world.get("entities") or {}).get(self.observer_id) or {})
            region = (
                ((nova.get("components") or {}).get("transform") or {}).get("region_id")
            )
            water = ((self.world.get("entities") or {}).get("water_01") or {})
            distribution = (
                (water.get("components") or {}).get("environmental_distribution") or {}
            )

            current_admission = [
                self.admission_memory.current(context)
                for context in self.admission_memory.current_contexts()
            ]
            state_counts = {"resolved": 0, "ambiguous": 0, "unsupported": 0}
            for item in current_admission:
                if item is not None:
                    state_counts[item.resolution_state] += 1

            return {
                "profile": "server-cognitive-rc1",
                "status": "ready",
                "cycle_id": self.cycle_id,
                "simulation_time": self.simulation_time,
                "world": {
                    "world_id": self.world.get("world_id"),
                    "tick": self.world.get("current_tick"),
                    "version": self.world.get("current_version"),
                    "events": len(self.world.get("events") or {}),
                    "deltas": len(self.world.get("deltas") or {}),
                },
                "nov": {
                    "region_id": region,
                    "needs": self._jsonable(self.needs),
                    "last_decision": self.last_decision,
                    "causal_memory_observations": len(self.gym.memory.snapshot()),
                    "situated_regimes": len(self.gym.regimes.entries),
                },
                "environment": {
                    "water_regions": sorted(
                        str(key)
                        for key, value in (distribution.get("by_region") or {}).items()
                        if isinstance(value, (int, float)) and value > 0
                    ),
                    "environmental_events": len(
                        [
                            event
                            for event in (self.world.get("events") or {}).values()
                            if str((event or {}).get("type") or "").startswith(
                                ("environment", "multimodal")
                            )
                        ]
                    ),
                },
                "bit_analyze": {
                    "pairwise_links": len(self.pairwise.links),
                    "higher_order_links": len(self.higher.links),
                    "known_slices": len(self.higher.slice_end_times),
                },
                "memoria_v2": {
                    "temporal_observations": len(self.temporal_memory.snapshot()),
                    "context_observations": len(self.context_memory.snapshot()),
                    "admission_snapshots": len(self.admission_memory.snapshot()),
                    "current_contexts": len(self.admission_memory.current_contexts()),
                    "current_resolution_counts": state_counts,
                },
                "event_time": {
                    "watermark": self.reorder.watermark,
                    "max_event_time": self.reorder.max_event_time,
                    "pending_slice_ids": self.reorder.pending_slice_ids(),
                    "late_rejections": len(self.rejections),
                },
                "persistence": {
                    "mode": "versioned-json-checkpoint",
                    "restart_safe": True,
                },
            }

    def soak_summary(self) -> dict[str, Any]:
        """Compact invariant-oriented view for unattended RC1 soak monitoring."""
        with self.lock:
            snapshot = self.snapshot()
            activity = tuple(self.activity)
            curiosity_cycles = sum(
                1
                for item in activity
                if item.get("kind") == "cycle" and item.get("nov_mode") == "curiosity"
            )
            need_cycles = sum(
                1
                for item in activity
                if item.get("kind") == "cycle" and item.get("nov_mode") == "need"
            )
            errors = sum(
                1 for item in activity if item.get("kind") == "error"
            )
            event_time = snapshot["event_time"]
            return {
                "profile": snapshot["profile"],
                "cycle_id": snapshot["cycle_id"],
                "simulation_time": snapshot["simulation_time"],
                "world_tick": snapshot["world"]["tick"],
                "world_version": snapshot["world"]["version"],
                "pairwise_links": snapshot["bit_analyze"]["pairwise_links"],
                "higher_order_links": snapshot["bit_analyze"]["higher_order_links"],
                "causal_memory_observations": snapshot["nov"]["causal_memory_observations"],
                "temporal_observations": snapshot["memoria_v2"]["temporal_observations"],
                "context_observations": snapshot["memoria_v2"]["context_observations"],
                "current_resolution_counts": snapshot["memoria_v2"]["current_resolution_counts"],
                "watermark": event_time["watermark"],
                "max_event_time": event_time["max_event_time"],
                "pending_slice_ids": event_time["pending_slice_ids"],
                "late_rejections": event_time["late_rejections"],
                "curiosity_cycles_in_activity_window": curiosity_cycles,
                "need_cycles_in_activity_window": need_cycles,
                "errors_in_activity_window": errors,
            }

    def activity_snapshot(self, limit: int = 50) -> tuple[dict[str, Any], ...]:
        with self.lock:
            limit = max(1, min(int(limit), len(self.activity) or 1))
            return tuple(list(self.activity)[-limit:])

    def debug_world(self) -> dict[str, Any]:
        with self.lock:
            return self._jsonable(self.world)

    def debug_memory(self) -> dict[str, Any]:
        with self.lock:
            return {
                "temporal": self._jsonable(self.temporal_memory.snapshot()),
                "context": self._jsonable(self.context_memory.snapshot()),
                "admission": self._jsonable(self.admission_memory.snapshot()),
                "causal": self._jsonable(self.gym.memory.snapshot()),
                "regimes": self._jsonable(self.gym.regimes),
            }
