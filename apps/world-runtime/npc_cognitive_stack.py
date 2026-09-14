from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from npc_audited_reordering_need_scheduler import NpcAuditedReorderingNeedScheduler
from npc_belief_model import NpcBeliefModel
from npc_causal_forecast import NpcCausalForecast
from npc_causal_model import NpcCausalModel
from npc_composite_strategy import NpcCompositeStrategy
from npc_composite_strategy_outcomes import NpcCompositeStrategyOutcomeProcessor
from npc_confidence_strategy import NpcConfidenceStrategy
from npc_counterfactual_simulator import NpcCounterfactualSimulator
from npc_decision_confidence import NpcDecisionConfidence
from npc_episodic_memory import NpcEpisodicMemory
from npc_goal_sequence import NpcGoalSequence
from npc_horizon_strategy import NpcHorizonStrategy
from npc_idle_wander import NpcIdleWander
from npc_need_dynamics import NpcNeedDynamics
from npc_need_horizon import NpcNeedHorizon
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
    belief_model: NpcBeliefModel
    causal_model: NpcCausalModel
    causal_forecast: NpcCausalForecast
    counterfactual_simulator: NpcCounterfactualSimulator
    need_horizon: NpcNeedHorizon
    goal_sequence: NpcGoalSequence
    decision_confidence: NpcDecisionConfidence
    strategy_value: NpcStrategyValue
    base_composite_strategy: NpcCompositeStrategy
    horizon_strategy: NpcHorizonStrategy
    composite_strategy: NpcConfidenceStrategy
    strategy_compiler: NpcStrategyCompiler
    strategy_executor: NpcStrategyExecutor
    need_scheduler: NpcNeedScheduler
    idle_wander: NpcIdleWander
    need_outcomes: NpcNeedOutcomeProcessor
    composite_strategy_outcomes: NpcCompositeStrategyOutcomeProcessor

    def world_tick_kwargs(self) -> dict[str, Any]:
        return {
            "npc_need_scheduler": self.need_scheduler,
            "npc_idle_wander": self.idle_wander,
            "npc_need_dynamics": self.need_dynamics,
            "npc_need_outcomes": self.need_outcomes,
            "npc_strategy_executor": self.strategy_executor,
            "npc_composite_strategy_outcomes": self.composite_strategy_outcomes,
            "npc_causal_model": self.causal_model,
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
    belief_model = NpcBeliefModel(root / "npc-beliefs.json", entity_provider=store)
    causal_model = NpcCausalModel(root / "npc-causal-hypotheses.json", world_provider=world_provider)
    causal_forecast = NpcCausalForecast(causal_model, root / "world-event-schedule.jsonl")
    counterfactual_simulator = NpcCounterfactualSimulator(causal_forecast)
    need_horizon = NpcNeedHorizon(urgency_threshold=need_threshold)
    goal_sequence = NpcGoalSequence()
    decision_confidence = NpcDecisionConfidence()
    strategy_value = NpcStrategyValue(
        planner,
        strategy_experience_provider=strategy_experience,
        episodic_memory_provider=episodic_memory,
        belief_provider=belief_model,
    )
    base_composite_strategy = NpcCompositeStrategy(
        planner,
        strategy_experience_provider=strategy_experience,
        causal_forecast_provider=causal_forecast,
        counterfactual_provider=counterfactual_simulator,
        need_state_provider=need_dynamics,
    )
    horizon_strategy = NpcHorizonStrategy(
        base_composite_strategy,
        need_horizon,
        goal_sequence_provider=goal_sequence,
    )
    composite_strategy = NpcConfidenceStrategy(horizon_strategy, decision_confidence)
    strategy_compiler = NpcStrategyCompiler()
    strategy_executor = NpcStrategyExecutor(root / "npc-strategy-executions.jsonl", plan_scheduler)
    need_scheduler = NpcAuditedReorderingNeedScheduler(
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
    idle_wander = NpcIdleWander(
        plan_scheduler,
        npc_ids=ids,
        interval_ticks=8,
        priority=25,
    )
    need_outcomes = NpcNeedOutcomeProcessor(
        root / "npc-need-outcomes.jsonl",
        ledger,
        need_dynamics,
        learning_provider=need_learning,
        strategy_experience_provider=strategy_experience,
        episodic_memory_provider=episodic_memory,
        belief_provider=belief_model,
    )
    composite_strategy_outcomes = NpcCompositeStrategyOutcomeProcessor(
        root / "npc-composite-strategy-outcomes.jsonl",
        strategy_executor,
        ledger,
        need_outcomes,
        strategy_experience,
    )

    return NpcCognitiveStack(
        need_dynamics=need_dynamics,
        need_learning=need_learning,
        strategy_experience=strategy_experience,
        episodic_memory=episodic_memory,
        belief_model=belief_model,
        causal_model=causal_model,
        causal_forecast=causal_forecast,
        counterfactual_simulator=counterfactual_simulator,
        need_horizon=need_horizon,
        goal_sequence=goal_sequence,
        decision_confidence=decision_confidence,
        strategy_value=strategy_value,
        base_composite_strategy=base_composite_strategy,
        horizon_strategy=horizon_strategy,
        composite_strategy=composite_strategy,
        strategy_compiler=strategy_compiler,
        strategy_executor=strategy_executor,
        need_scheduler=need_scheduler,
        idle_wander=idle_wander,
        need_outcomes=need_outcomes,
        composite_strategy_outcomes=composite_strategy_outcomes,
    )
