# NPC Need Horizon 001

## Goal

Add a bounded planning layer that detects when satisfying the current need is likely to leave another internal need urgent immediately afterwards.

The horizon layer is deterministic, read-only and does not mutate world state, persistent need state, episodic memory or learning.

## Inputs

The planner consumes:

- the current need being considered;
- predicted terminal satisfaction for that need;
- the counterfactual strategy result, especially `end_needs`.

The counterfactual simulator itself remains conservative and never grants imagined satisfaction. The horizon planner applies a separate conditional assumption only for ordering future actions:

> if the current strategy succeeds with its predicted satisfaction, what need is likely to be urgent next?

That assumed state exists only inside the horizon assessment.

## Utility

Future needs use the same priority structure as the runtime:

- safety: 1000
- energy: 700
- social: 400
- curiosity: 200

`utility = severity * priority`

A need is considered urgent when it reaches the configured threshold, initially `0.70`.

## Output

`NpcNeedHorizon.assess()` returns:

- `counterfactual_end_needs`
- `conditional_post_outcome_needs`
- `ranked_future_needs`
- `next_urgent_need`
- `defer_to_need`
- `recommended_need_sequence`
- `competing_need_pressure`

Example:

```text
current: curiosity
counterfactual end energy: 0.82
conditional curiosity after expected satisfaction: 0.55

recommended sequence:
curiosity -> energy
```

If a higher-priority need dominates by the configured margin:

```text
current: curiosity
future safety: 0.85

=> defer_to_need = safety
```

## Strategy overlay

`NpcHorizonStrategy` wraps the existing composite strategy ranker. It applies a bounded penalty to strategies that are projected to create stronger competing need pressure.

This overlay is used only while strategy evidence is still heuristic. If full-strategy empirical evidence is mature, horizon pressure does not modify that empirical score.

This preserves the evidence precedence:

```text
mature empirical strategy evidence
    > short-horizon projection
    > raw heuristic
```

## Epistemic boundary

The horizon state is a planning assumption, not a remembered event and not a learned fact.

It MUST NOT:

- write to `NpcNeedDynamics`;
- create an episodic memory entry;
- update strategy experience;
- create a belief or causal hypothesis;
- mutate authoritative world state.

Only real execution outcomes may perform those updates.

## Next step

After this baseline is validated, `defer_to_need` can be used by an explicit scheduling policy to reorder goals, e.g.:

```text
explore now
vs.
rest first -> explore later
```

That scheduler change should be implemented separately from horizon inference so reasoning and authority remain distinct.
