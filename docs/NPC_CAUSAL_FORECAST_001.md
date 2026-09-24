# NPC Causal Forecast 001

## Goal

Allow deterministic NPC strategy ranking to anticipate a likely future world transition without promoting a provisional causal hypothesis to fact.

The baseline connects three already-authoritative sources:

```text
logical schedule ledger
        +
provisional causal hypothesis
        +
current NPC decision context
        ↓
bounded consequence forecast
```

No forecast mutates the world and no LLM is involved.

## Temporal gate

`NpcNeedScheduler` now carries `logical_tick` inside the decision/learning context.

`NpcCausalForecast` reads the append-only `world-event-schedule.jsonl` ledger and identifies the next scheduled `environment.period` transition.

A forecast is returned only when:

1. a future period transition exists;
2. the candidate strategy is estimated to still be executing when that transition occurs;
3. a matching `NpcCausalModel` hypothesis exists;
4. causal confidence is at least the configured minimum.

Therefore a short action that completes before nightfall is not penalized merely because night exists later in the schedule.

## Bounded epistemic weight

The causal model remains provisional. The forecast exposes:

```text
current_danger
projected_danger
mean_effect_delta
confidence
blend
source hypothesis
scheduled transition provenance
```

The default maximum blend is bounded. A causal prior can adjust heuristic strategy risk but cannot become an authoritative world fact.

## Strategy exposure

The first deterministic exposure policy is intentionally simple and explainable:

```text
direct             -> exposure 1.00
via_shelter:*      -> exposure 0.50
wait_then_direct   -> exposure 0.80
```

This means the same anticipated increase in environmental danger may penalize a direct trip more than a route that deliberately passes through a safe shelter.

These coefficients are policy, not learned truth. Future empirical strategy evidence may replace them.

## Empirical precedence

If `NpcStrategyExperience` reports mature evidence for a strategy in the same context, the causal forecast is ignored for that strategy.

The precedence is:

```text
mature empirical strategy evidence
        >
provisional causal anticipation
        >
static route/risk heuristic
```

This prevents double-counting experience and keeps the causal layer useful mainly before direct strategy statistics are mature.

## Example

Suppose Nov is deciding near nightfall:

```text
current tick = 35
next night event = tick 36
learned provisional relation:
  day -> night
  danger_level tends to increase
```

A strategy estimated to finish before tick 36 receives no forecast.

A longer strategy crossing tick 36 receives a bounded projected-risk adjustment. `via_shelter` receives less future-risk exposure than `direct`, so it may become preferable when the evidence and expected transition are strong enough.

The system is not asserting:

> night causes danger.

It is reasoning:

> repeated observations suggest that this scheduled transition has often been followed by higher danger; this candidate action may still be active then, so account for that possibility with limited weight.

## Files

- `apps/world-runtime/npc_causal_forecast.py`
- `apps/world-runtime/npc_causal_model.py`
- `apps/world-runtime/npc_composite_strategy.py`
- `apps/world-runtime/npc_need_scheduler.py`
- `tests/test_npc_causal_forecast.py`

## Invariants

1. forecasts never mutate authoritative state;
2. schedule timing comes from the persistent logical event ledger, not wall-clock time;
3. causal hypotheses remain provisional;
4. low-confidence hypotheses do not forecast;
5. strategies completing before the transition are unaffected;
6. mature empirical strategy evidence disables the causal prior;
7. all ranking remains deterministic and auditable.
