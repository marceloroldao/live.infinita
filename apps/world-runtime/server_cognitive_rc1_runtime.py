from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from memoria_resolutiva.situated_live_gym_v2 import SituatedLiveCognitiveGymV2

from closed_loop_runtime import execute_validated_action
from distributed_environment_runtime import advance_distributed_environmental_agents
from environmental_multisensor_runtime import sample_multimodal_sensor_frame
from nov_autonomous_life import choose_autonomous_action, needs_after_committed_action
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
    cycles: int = 0
    last_decision: Any = None
    last_cognitive_step: Any = None

    @classmethod
    def create(cls, *, episode_id: int = 1):
        world = build_server_cognitive_rc1_world(episode_id=episode_id)
        return cls(
            world=world,
            needs=initial_server_cognitive_rc1_needs(world),
            gym=SituatedLiveCognitiveGymV2(
                min_independent_episodes=2,
                min_contiguous_support=2,
            ),
        )

    def step(self) -> dict[str, Any]:
        profile = self.world["rules"]["server_cognitive_rc1"]
        observer_id = str(profile["observer_id"])

        environmental = advance_distributed_environmental_agents(
            self.world,
            ticks=int(profile["environment_ticks_between_frames"]),
        )
        self.world = environmental[-1].world

        sensor_frames = []
        for _ in range(int(profile["sensor_frames_per_cycle"])):
            sampled = sample_multimodal_sensor_frame(
                self.world,
                observer_id=observer_id,
            )
            self.world = sampled.world
            sensor_frames.append(sampled.frame_id)

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
            sensor_frames=tuple(sensor_frames),
            consequence_address=execution.consequence_address,
        )

    def run(self, cycles: int) -> tuple[dict[str, Any], ...]:
        if cycles < 1:
            raise ValueError("cycles must be >= 1")
        return tuple(self.step() for _ in range(cycles))

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
                "memory_episodes": len(self.gym.memory.snapshot()),
                "active_regime": active,
                "pending_regime": pending,
                "consequence_address": consequence_address,
            },
            "sensors": {
                "frame_ids": sensor_frames,
            },
        }
