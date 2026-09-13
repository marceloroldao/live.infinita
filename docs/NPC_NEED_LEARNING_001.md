# NPC Need Learning 001

## Goal

Allow an NPC to accumulate evidence about which configured targets actually satisfy a need better, without a neural network, stochastic policy, or direct world mutation.

## State

`NpcNeedLearning` persists compact statistics per:

`npc_id + need + target_entity_id`

Each entry stores:

- observation count;
- online mean satisfaction;
- last outcome id;
- last plan/proposal provenance.

Outcomes are idempotent by `outcome_id`.

## Learning rule

For an observed satisfaction `r` and previous mean `m` after `n` samples:

`m' = m + (r - m) / (n + 1)`

Only the actually achieved reduction of the need is observed, not the configured maximum reward.

## Deterministic exploration

There is no random epsilon-greedy policy.

A target with fewer than `exploration_samples` observations is preferred before exploitation. Among under-sampled targets, the least sampled target wins, then stable target id. Once every candidate reaches the minimum sample count, the highest empirical mean wins, then evidence count, then stable target id.

This avoids early lock-in while preserving replayable selection.

## Target configuration

Legacy singular fields remain supported:

- `safety_target_entity_id`
- `rest_target_entity_id`
- `social_target_entity_id`
- `curiosity_target_entity_id`

Optional candidate lists can now be supplied:

- `safety_target_entity_ids`
- `rest_target_entity_ids`
- `social_target_entity_ids`
- `curiosity_target_entity_ids`

Only targets that still exist are eligible.

## Data flow

Need Dynamics
→ Need Scheduler
→ learned target ranking
→ Proposal Ledger
→ Plan
→ authoritative execution
→ completed plan
→ Need Outcome Processor
→ internal satisfaction
→ NpcNeedLearning observation

Learning never bypasses the Proposal Ledger, planner, arbiter, or Mutation Gate.

## Scale

Learning is bounded by configured NPCs and their candidate targets. It does not scan the full cold universe.
