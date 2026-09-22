from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2
from memoria_resolutiva.structural_context_admission_state_v2 import (
    StructuralContextAdmissionStateMemory,
)
from memoria_resolutiva.structural_context_observation_v2 import (
    StructuralContextObservationMemory,
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
    policy_from_world,
    resolve_higher_order_context_states,
    select_higher_order_context_candidates,
)
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
from reality_slice_bridge import reality_window_from_world_rule
from reality_slice_event_time_runtime import ingest_reality_slice_event_time
from scenario_server_cognitive_rc1 import (
    build_server_cognitive_rc1_world,
    initial_server_cognitive_rc1_needs,
)


def _actual_candidate_id(request, consequence_address: str) -> str:
    consequence = (consequence_address,)
    return next(
        candidate.candidate_id
        for candidate in request.candidates
        if candidate.consequence_addresses == consequence
    )


@dataclass(slots=True)
class ServerCognitiveRC1Runtime:
    world: dict[str, Any]
    needs: Any
    gym: SituatedLiveCognitiveGymV2
    pairwise: Any
    higher: Any
    reorder: RealitySliceReorderBuffer
    context_memory: StructuralContextObservationMemory
    admission_memory: StructuralContextAdmissionStateMemory
    provenance_by_slice: dict[int, tuple[str, ...]] = field(default_factory=dict)
    cycles: int = 0
    simulation_time: float = 0.0
    reality_slices_offered: int = 0
    reality_slices_ingested: int = 0
    late_rejection_count: int = 0
    recent_late_rejections: list[dict[str, Any]] = field(default_factory=list)
    last_window_id: int | None = None
    last_ingested_slice_ids: tuple[int, ...] = ()
    last_candidates: tuple[Any, ...] = ()
    last_resolutions: tuple[Any, ...] = ()
    last_decision: Any = None
    last_cognitive_step: Any = None

    @classmethod
    def create(cls, *, episode_id: int = 1):
        world = build_server_cognitive_rc1_world(episode_id=episode_id)
        higher_policy = policy_from_world(world)
        event_time = world["rules"]["reality_slice_event_time"]
        return cls(
            world=world,
            needs=initial_server_cognitive_rc1_needs(world),
            gym=SituatedLiveCognitiveGymV2(
                min_independent_episodes=2,
                min_contiguous_support=2,
            ),
            pairwise=TemporalAssociator(lambda0=0.0),
            higher=make_sparse_context_associator(higher_policy),
            reorder=RealitySliceReorderBuffer(
                allowed_lateness=float(event_time["allowed_lateness"])
            ),
            context_memory=StructuralContextObservationMemory(),
            admission_memory=StructuralContextAdmissionStateMemory(),
        )

    def _record_rejections(self, rejections) -> None:
        for item in rejections:
            self.late_rejection_count += 1
            self.recent_late_rejections.append(
                {
                    "slice_id": int(item.slice_id),
                    "event_time": float(item.event_time),
                    "watermark": float(item.watermark),
                    "reason": str(item.reason),
                }
            )
        if len(self.recent_late_rejections) > 32:
            del self.recent_late_rejections[:-32]

    def _sample_temporal_window(self, *, observer_id: str) -> tuple[str, ...]:
        profile = self.world["rules"]["server_cognitive_rc1"]
        frame_ids: list[str] = []

        for _ in range(int(profile["sensor_frames_per_cycle"])):
            environmental = advance_distributed_environmental_agents(
                self.world,
                ticks=int(profile["environment_ticks_between_frames"]),
            )
            self.world = environmental[-1].world

            sampled = sample_multimodal_sensor_frame(
                self.world,
                observer_id=observer_id,
            )
            self.world = sampled.world
            frame_ids.append(sampled.frame_id)

        window = reality_window_from_world_rule(
            self.world,
            observer_id=observer_id,
            time_origin=self.simulation_time,
        )
        self.last_window_id = int(window.reality_slice.slice_id)
        self.reality_slices_offered += 1
        self.provenance_by_slice[int(window.reality_slice.slice_id)] = tuple(
            window.frame_ids
        )

        ingest = ingest_reality_slice_event_time(
            self.reorder,
            self.pairwise,
            self.higher,
            window.reality_slice,
        )
        self._record_rejections(ingest.batch.rejected)
        self.last_ingested_slice_ids = tuple(ingest.ingested_slice_ids)
        self.reality_slices_ingested += len(ingest.ingested_slice_ids)

        if ingest.ingested_slice_ids:
            policy = policy_from_world(self.world)
            candidates = select_higher_order_context_candidates(
                self.pairwise,
                self.higher,
                policy,
                provenance_by_slice=self.provenance_by_slice,
            )
            for candidate in candidates:
                ingest_higher_order_context_candidate(
                    self.context_memory,
                    candidate,
                )
            resolutions = resolve_higher_order_context_states(
                self.pairwise,
                self.higher,
                policy,
            )
            refresh_higher_order_context_resolution_state(
                self.admission_memory,
                resolutions,
                source_epoch_id=f"server-cycle-{self.cycles + 1}",
                supporting_slice_ids=tuple(ingest.ingested_slice_ids),
            )
            self.last_candidates = candidates
            self.last_resolutions = resolutions

        self.simulation_time += float(profile["simulation_time_step"])
        return tuple(frame_ids)

    def step(self) -> dict[str, Any]:
        profile = self.world["rules"]["server_cognitive_rc1"]
        observer_id = str(profile["observer_id"])

        sensor_frames = self._sample_temporal_window(observer_id=observer_id)

        decision = choose_autonomous_action(
            gym=self.gym,
            world=self.world,
            needs=self.needs,
            observer_id=observer_id,
        )
        execution = execute_validated_action(
            self.world,
            decision.proposal,
        )
        actual_id = _actual_candidate_id(
            decision.request,
            execution.consequence_address,
        )
        cognitive_step = self.gym.step(
            decision.request,
            actual_candidate_id=actual_id,
            learn=True,
        )
        self.world = execution.world
        self.needs = needs_after_committed_action(
            decision=decision,
            result_tick=int(self.world["current_tick"]),
        )
        self.cycles += 1
        self.last_decision = decision
        self.last_cognitive_step = cognitive_step
        return self.status(
            sensor_frames=sensor_frames,
            consequence_address=execution.consequence_address,
        )

    def run(self, cycles: int) -> tuple[dict[str, Any], ...]:
        if cycles < 1:
            raise ValueError("cycles must be >= 1")
        return tuple(self.step() for _ in range(cycles))

    def _resolution_counts(self) -> dict[str, int]:
        counts = {"resolved": 0, "ambiguous": 0, "unsupported": 0}
        for item in self.last_resolutions:
            state = str(item.resolution_state)
            counts[state] = counts.get(state, 0) + 1
        return counts

    def status(
        self,
        *,
        sensor_frames: tuple[str, ...] = (),
        consequence_address: str | None = None,
    ) -> dict[str, Any]:
        water = self.world["entities"]["water_01"]["components"][
            "environmental_distribution"
        ]
        decision = self.last_decision
        step = self.last_cognitive_step
        active = None
        pending = None
        if step is not None:
            active_regime = step.current_regime.active
            pending_regime = step.current_regime.pending
            active = (
                tuple(active_regime.consequence_addresses)
                if active_regime is not None
                else None
            )
            pending = (
                tuple(pending_regime.consequence_addresses)
                if pending_regime is not None
                else None
            )

        return {
            "profile": "server-cognitive-rc1",
            "cycles": self.cycles,
            "simulation_time": self.simulation_time,
            "world": {
                "world_id": self.world["world_id"],
                "tick": int(self.world["current_tick"]),
                "version": int(self.world["current_version"]),
                "events": len(self.world.get("events") or {}),
                "deltas": len(self.world.get("deltas") or {}),
            },
            "nov": {
                "mode": decision.mode if decision is not None else None,
                "action": (
                    decision.proposal["action"]
                    if decision is not None
                    else None
                ),
                "needs": {
                    "roam": self.needs.pressure("roam"),
                    "recover": self.needs.pressure("recover"),
                },
            },
            "environment": {
                "water_by_region": dict(sorted(water["by_region"].items())),
                "water_evaporated_total": int(water["evaporated_total"]),
            },
            "cognition": {
                "causal": {
                    "memory_episodes": len(self.gym.memory.snapshot()),
                    "active_regime": active,
                    "pending_regime": pending,
                    "consequence_address": consequence_address,
                },
                "structural": {
                    "pairwise_links": len(self.pairwise.links),
                    "higher_order_links": len(self.higher.links),
                    "historical_context_records": len(
                        self.context_memory.snapshot()
                    ),
                    "admission_snapshots": len(
                        self.admission_memory.snapshot()
                    ),
                    "current_contexts": len(
                        self.admission_memory.current_contexts()
                    ),
                    "current_candidates": len(self.last_candidates),
                    "resolution_counts": self._resolution_counts(),
                },
            },
            "event_time": {
                "watermark": self.reorder.watermark,
                "max_event_time": self.reorder.max_event_time,
                "pending_slice_ids": self.reorder.pending_slice_ids(),
                "last_window_id": self.last_window_id,
                "last_ingested_slice_ids": self.last_ingested_slice_ids,
                "slices_offered": self.reality_slices_offered,
                "slices_ingested": self.reality_slices_ingested,
                "late_rejection_count": self.late_rejection_count,
                "recent_late_rejections": tuple(
                    self.recent_late_rejections
                ),
            },
            "sensors": {
                "frame_ids": sensor_frames,
            },
            "persistence": {
                "mode": "memory-only",
                "restart_safe": False,
            },
        }
