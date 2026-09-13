from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from npc_composite_strategy import NpcCompositeStrategy
from npc_composite_strategy_outcomes import NpcCompositeStrategyOutcomeProcessor
from npc_episodic_memory import NpcEpisodicMemory
from npc_need_dynamics import NpcNeedDynamics
from npc_need_learning import NpcNeedLearning
from npc_need_outcomes import NpcNeedOutcomeProcessor
from npc_need_scheduler import NpcNeedScheduler
from npc_strategy_compiler import NpcStrategyCompiler
from npc_strategy_executor import NpcStrategyExecutor
from npc_strategy_experience import NpcStrategyExperience
from npc_strategy_value import NpcStrategyValue


@dataclass(frozen=True)
class NpcCognitiveStack:
    """Explicit composition root for deterministic NPC cognition."""

    need_dynamics: NpcNeedDynamics
    need_learning: NpcNeedLearning
    strategy_experience: NpcStrategyExperience
    episodic_memory: NpcEpisodicMemory
    strategy_value: NpcStrategyValue
    composite_strategy: NpcCompositeStrategy
    strategy_compiler: NpcStrategyCompiler
    strategy_executor: NpcStrategyExecutor
    need_scheduler: NpcNeedScheduler
    need_outcomes: NpcNeedOutcomeProcessor
    composite_strategy_outcomes: NpcCompositeStrategyOutcomeProcessor

    def world_tick_kwargs(self) -> dict[str, Any]:
        return {
            "npc_need_scheduler": self.need_scheduler,
            "npc_need_dynamics": self.need_dynamics,
            "npc_need_outcomes": self.need_outcomes,
            "npc_strategy_executor": self.strategy_executor,
            "npc_composite_strategy_outcomes": self.composite_strategy_outcomes,
        }


def build_npc_cognitive_stack(
    *,
    data_dir: Path,
    proposal_ledger: Any,
    plan_scheduler: Any,
    npc_ids: list[str],
    world_provider: Any | None = None,
    need_threshold: float = 0.70,
    cooldown_ticks: int = 20,
    target_exploration_samples: int = 2,
    contextual_min_samples: int = 2,
    strategy_min_samples: int = 2,
) -> NpcCognitiveStack:
    root = Path(data_dir)
    root.mkdir(parents=True, exist_ok=True)
    ids = sorted({str(value).strip() for value in npc_ids if str(value).strip()})
    if not ids:
        raise ValueError("npc_ids must contain at least one entity id")

    planner = getattr(plan_scheduler, "planner", None)
    store = getattr(planner, "store", None)
    ledger = getattr(plan_scheduler, "ledger", None)
    if planner is None or store is None:
        raise ValueError("plan_scheduler.planner.store is required")
    if ledger is None:
        raise ValueError("plan_scheduler.ledger is required")

    need_dynamics = NpcNeedDynamics(root / "npc-need-state.json", store, npc_ids=ids, world_provider=world_provider)
    need_learning = NpcNeedLearning(
        root / "npc-need-learning.json",
        exploration_samples=target_exploration_samples,
        contextual_min_samples=contextual_min_samples,
    )
    strategy_experience = NpcStrategyExperience(root / "npc-strategy-experience.json", min_samples=strategy_min_samples)
    episodic_memory = NpcEpisodicMemory(root / "npc-episodes.jsonl")
    strategy_value = NpcStrategyValue(
        planner,
        strategy_experience_provider=strategy_experience,
        episodic_memory_provider=episodic_memory,
    )
    composite_strategy = NpcCompositeStrategy(planner, strategy_experience_provider=strategy_experience)
    strategy_compiler = NpcStrategyCompiler()
    strategy_executor = NpcStrategyExecutor(root / "npc-strategy-executions.jsonl", plan_scheduler)
    need_scheduler = NpcNeedScheduler(
        root / "npc-need-scheduler.jsonl",
        proposal_ledger,
        plan_scheduler,
        npc_ids=ids,
        threshold=need_threshold,
        cooldown_ticks=cooldown_ticks,
        need_state_provider=need_dynamics,
        learning_provider=need_learning,
        world_provider=world_provider,
        strategy_provider=strategy_value,
        composite_strategy_provider=composite_strategy,
        strategy_compiler=strategy_compiler,
        strategy_executor=strategy_executor,
    )
    need_outcomes = NpcNeedOutcomeProcessor(
        root / "npc-need-outcomes.jsonl",
        ledger,
        need_dynamics,
        learning_provider=need_learning,
        strategy_experience_provider=strategy_experience,
        episodic_memory_provider=episodic_memory,
    )
    composite_strategy_outcomes = NpcCompositeStrategyOutcomeProcessor(
        root / "npc-composite-strategy-outcomes.jsonl",
        strategy_executor,
        ledger,
        need_outcomes,
        strategy_experience,
        episodic_memory_provider=episodic_memory,
    )

    return NpcCognitiveStack(
        need_dynamics=need_dynamics,
        need_learning=need_learning,
        strategy_experience=strategy_experience,
        episodic_memory=episodic_memory,
        strategy_value=strategy_value,
        composite_strategy=composite_strategy,
        strategy_compiler=strategy_compiler,
        strategy_executor=strategy_executor,
        need_scheduler=need_scheduler,
        need_outcomes=need_outcomes,
        composite_strategy_outcomes=composite_strategy_outcomes,
    )
