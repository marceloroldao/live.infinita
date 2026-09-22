from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
import pickle
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


CHECKPOINT_FORMAT = "live.infinita/server-cognitive-rc1"
CHECKPOINT_VERSION = 1


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
    pairwise: TemporalAssociator
    higher: Any
    reorder: RealitySliceReorderBuffer
    context_memory: StructuralContextObservationMemory
    context_admission: StructuralContextAdmissionStateMemory
    provenance_by_slice: dict[int, tuple[str, ...]] = field(default_factory=dict)
    ingested_slice_ids: list[int] = field(default_factory=list)
    late_rejections: list[Any] = field(default_factory=list)
    cycles: int = 0
    simulation_time: float = 0.0
    last_decision: Any = None
    last_cognitive_step: Any = None
    last_reality_slice_id: int | None = None
    last_candidates: tuple[Any, ...] = ()
    last_resolutions: tuple[Any, ...] = ()

    @classmethod
    def create(cls, *, episode_id: int = 1):
        world = build_server_cognitive_rc1_world(episode_id=episode_id)
        policy = policy_from_world(world)
        event_time = world["rules"]["reality_slice_event_time"]
        return cls(
            world=world,
            needs=initial_server_cognitive_rc1_needs(world),
            gym=SituatedLiveCognitiveGymV2(
                min_independent_episodes=2,
                min_contiguous_support=2,
            ),
            pairwise=TemporalAssociator(lambda0=0.0),
            higher=make_sparse_context_associator(policy),
            reorder=RealitySliceReorderBuffer(
                allowed_lateness=float(event_time["allowed_lateness"])
            ),
            context_memory=StructuralContextObservationMemory(),
            context_admission=StructuralContextAdmissionStateMemory(),
        )

    @classmethod
    def load_checkpoint(cls, path: str | os.PathLike[str]):
        """Restore an RC1 checkpoint from a trusted local file only."""
        source = Path(path)
        with source.open("rb") as handle:
            payload = pickle.load(handle)
        if not isinstance(payload, dict):
            raise ValueError("invalid server cognitive checkpoint")
        if payload.get("format") != CHECKPOINT_FORMAT:
            raise ValueError("checkpoint format mismatch")
        if int(payload.get("version", -1)) != CHECKPOINT_VERSION:
            raise ValueError("checkpoint version mismatch")
        runtime = payload.get("runtime")
        if not isinstance(runtime, cls):
            raise ValueError("checkpoint does not contain ServerCognitiveRC1Runtime")
        return runtime

    def save_checkpoint(self, path: str | os.PathLike[str]) -> Path:
        """Atomically persist exact experimental runtime state to a trusted local path."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        payload = {
            "format": CHECKPOINT_FORMAT,
            "version": CHECKPOINT_VERSION,
            "cycles": self.cycles,
            "world_id": self.world.get("world_id"),
            "runtime": self,
        }
        with temporary.open("wb") as handle:
            pickle.dump(payload, handle, protocol=pickle.HIGHEST_PROTOCOL)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        return target

    def _sample_reality_window(self) -> tuple[tuple[str, ...], Any]:
        profile = self.world["rules"]["server_cognitive_rc1"]
        observer_id = str(profile["observer_id"])
        sensor_frames: list[str] = []

        # Each frame must represent a distinct world tick. Sampling three copies of
        # one tick would make the structural trajectory simultaneous by construction.
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
            sensor_frames.append(sampled.frame_id)

        window = reality_window_from_world_rule(
            self.world,
            observer_id=observer_id,
            time_origin=self.simulation_time,
        )
        self.simulation_time += float(profile["simulation_time_step"])
        self.last_reality_slice_id = int(window.reality_slice.slice_id)
        self.provenance_by_slice[self.last_reality_slice_id] = tuple(
            window.frame_ids
        )
        return tuple(sensor_frames), window

    def _ingest_structural_window(self, window) -> tuple[int, ...]:
        result = ingest_reality_slice_event_time(
            self.reorder,
            self.pairwise,
            self.higher,
            window.reality_slice,
        )
        ingested = tuple(int(value) for value in result.ingested_slice_ids)
        self.ingested_slice_ids.extend(ingested)
        self.late_rejections.extend(result.batch.rejected)

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
            self.context_admission,
            resolutions,
            source_epoch_id=f"server-cycle-{self.cycles + 1:08d}",
            supporting_slice_ids=ingested,
        )
        self.last_candidates = candidates
        self.last_resolutions = resolutions
        return ingested

    def step(self) -> dict[str, Any]:
        profile = self.world["rules"]["server_cognitive_rc1"]
        observer_id = str(profile["observer_id"])

        sensor_frames, window = self._sample_reality_window()
        ingested_slice_ids = self._ingest_structural_window(window)

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
            ingested_slice_ids=ingested_slice_ids,
        )

    def run(self, cycles: int) -> tuple[dict[str, Any], ...]:
        if cycles < 1:
            raise ValueError("cycles must be >= 1")
        return tuple(self.step() for _ in range(cycles))

    def _resolution_counts(self) -> dict[str, int]:
        counts = {
            "resolved": 0,
            "ambiguous": 0,
            "unsupported": 0,
        }
        for resolution in self.last_resolutions:
            state = str(resolution.resolution_state)
            counts[state] = counts.get(state, 0) + 1
        return counts

    def _last_rejection_payload(self):
        if not self.late_rejections:
            return None
        item = self.late_rejections[-1]
        return {
            "slice_id": int(item.slice_id),
            "event_time": float(item.event_time),
            "watermark": float(item.watermark),
            "reason": str(item.reason),
        }

    def status(
        self,
        *,
        sensor_frames: tuple[str, ...] = (),
        consequence_address: str | None = None,
        ingested_slice_ids: tuple[int, ...] = (),
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
                "intervention_memory_episodes": len(self.gym.memory.snapshot()),
                "active_regime": active,
                "pending_regime": pending,
                "pairwise_patterns": len(self.pairwise.pattern_slices),
                "pairwise_links": len(self.pairwise.links),
                "higher_order_links": len(self.higher.links),
                "higher_order_candidates": len(self.last_candidates),
                "context_observations": len(self.context_memory.snapshot()),
                "admission_snapshots": len(self.context_admission.snapshot()),
                "resolution_counts": self._resolution_counts(),
                "consequence_address": consequence_address,
            },
            "reality": {
                "last_slice_id": self.last_reality_slice_id,
                "ingested_slice_ids": ingested_slice_ids,
                "ingested_total": len(self.ingested_slice_ids),
                "frame_ids": sensor_frames,
            },
            "event_time": {
                "max_event_time": self.reorder.max_event_time,
                "watermark": self.reorder.watermark,
                "pending_slice_ids": self.reorder.pending_slice_ids(),
                "late_rejections": len(self.late_rejections),
                "last_rejection": self._last_rejection_payload(),
            },
        }

    def inspect(self) -> dict[str, Any]:
        return {
            "status": self.status(),
            "higher_order_candidates": tuple(
                candidate.to_payload()
                for candidate in self.last_candidates
            ),
            "current_resolutions": tuple(
                {
                    "antecedent_pattern_addresses": tuple(
                        f"temporal:pattern:{value}"
                        for value in resolution.antecedent_patterns
                    ),
                    "resolution_state": resolution.resolution_state,
                    "active_candidate_ids": resolution.active_candidate_ids,
                    "competing_candidate_ids": resolution.competing_candidate_ids,
                    "hypotheses": tuple(
                        {
                            "candidate_id": item.candidate_id,
                            "consequence_pattern_address": (
                                f"temporal:pattern:{item.consequence_pattern}"
                            ),
                            "rho": item.rho,
                            "repetitions": item.repetitions,
                            "context_coverage": item.context_coverage,
                            "context_reliability": item.context_reliability,
                            "supporting_slice_ids": item.supporting_slice_ids,
                            "admitted": item.admitted,
                        }
                        for item in resolution.hypotheses
                    ),
                }
                for resolution in self.last_resolutions
            ),
            "historical_context_observations": tuple(
                asdict(item)
                for item in self.context_memory.snapshot()
            ),
            "admission_history": tuple(
                asdict(item)
                for item in self.context_admission.snapshot()
            ),
        }
