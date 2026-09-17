# Nov Autonomous Scenario 001

## Goal

Provide the first deterministic autonomous-world baseline in which Nov can generate and execute goals without external audience, operator or LLM input.

The scenario is intentionally small and observable. It is a runtime fixture, not a production activation.

## Bootstrap

`examples/world-state.nov-autonomous.bootstrap.json`

Regions:

- `clearing` — Nov starts here; contains the campfire.
- `shelter` — contains Nov's bed and a safe-place marker.
- `deep_forest` — contains the ancient tree used as a curiosity target.

Topology:

```text
shelter <-> clearing <-> deep_forest
```

## Nov initial state

Initial compact-need source values are stored on the cold entity and are lazily materialized into `NpcNeedDynamics` on the first logical tick.

```text
safety    = 0.20
energy    = 0.86
social    = 0.10
curiosity = 0.74
```

The first utility winner is therefore energy:

```text
energy utility = 0.86 * 700 = 602
curiosity      = 0.74 * 200 = 148
```

The first energy target is deliberately unambiguous:

```text
rest_target_entity_id = bed_nov
```

This keeps the first autonomous cycle deterministic. The campfire remains present as a reactive world object, but is not initially an energy target.

## Expected first autonomous cycle

```text
logical tick
  -> need dynamics initializes/advances
  -> energy wins utility arbitration
  -> Proposal Ledger receives the semantic goal
  -> composite strategy is selected/compiled
  -> PlanScheduler creates authoritative movement child plan(s)
  -> Mutation Gate validates every world mutation
  -> Nov crosses from clearing to shelter
  -> terminal energy outcome is applied exactly once
  -> energy need decreases
  -> one concrete episode is persisted
  -> later ticks may generate a different goal, such as curiosity toward deep_forest
```

The test does not require Nov to remain at the shelter forever. Once the energy outcome is applied, a later need is allowed to become dominant and create another goal. The invariant is the causal sequence: energy goal first, shelter visited, energy outcome applied, need reduced and concrete experience persisted.

## Logical day/night cycle

The bootstrap declares persistent world schedules. The autonomous runtime imports them into `WorldEventScheduler` using stable idempotency keys, so rebuilding or restarting the runtime does not duplicate the schedule.

```text
tick 12 -> night, danger_level=0.35
tick 24 -> day,   danger_level=0.05
tick 36 -> night, danger_level=0.35
tick 48 -> day,   danger_level=0.05
...
```

Each phase recurs every 24 logical ticks. The events pass through the same `Mutation Gate` as every other authoritative world mutation. A restart does not replay missed wall-clock time and does not create duplicate day/night events.

The period is therefore not cosmetic state. `NpcNeedDynamics` reads the resulting environmental `danger_level` during the same logical tick. At night the safety need trends upward; when daytime returns and environmental risk falls, the safety need trends downward again. This keeps environmental evolution and NPC motivation causally connected without a special-case AI rule.

## Declarative world reactions

The same bootstrap also declares state-triggered reactions that are installed into `ConditionalEventScheduler` with stable idempotency keys. These conditions are evaluated after scheduled world events and before NPC need dynamics.

The first reactions are deliberately simple and visible:

```text
night AND campfire.lit == false -> campfire.lit = true
day   AND campfire.lit == true  -> campfire.lit = false
```

The compound condition includes the current campfire state so startup does not produce a redundant mutation. When tick 12 turns the world to night, the conditional phase sees the new state in the same tick and lights the campfire. Tick 24 restores day and the next conditional phase turns the fire off. Both changes are authoritative cold-store mutations and still pass through the `Mutation Gate`.

This establishes the first complete reactive chain:

```text
logical time
  -> environment changes
  -> world object reacts
  -> NPC internal dynamics observe the new environment
  -> future goals can change
```

No LLM or renderer frame is involved in that causal chain.

## Episodic memory

`NpcEpisodicMemory` adds an append-only record of concrete NPC experience under `npc-episodes.jsonl`. It is deliberately separate from `NpcStrategyExperience`: the latter stores statistical aggregates, while episodic memory preserves individual events that can later be recalled or sent to Memoria.ia.

An episode is created at the `NpcNeedOutcomeProcessor` boundary, in the same logical tick in which a completed need-driven plan actually changes Nov's internal state. This avoids delaying memory until a composite-strategy wrapper notices completion on a later tick.

Each `npc_episode_v1` record preserves:

```text
episode_id
npc_id
logical_tick
need
target_entity_id
strategy_id
context:
  period
  weather
  region_id
  danger_level
  danger_bucket
outcome:
  satisfaction
  elapsed_ticks
  preemptions
  replans
  observed_risk
source:
  need_outcome provenance
  plan_id
  proposal_id
  plan_revision
```

Episode ids are deterministic per completed plan (`plan:<plan_id>`), so replay/reprocessing does not duplicate memory. Recall is also deterministic and local: semantic matches (`need`, target, strategy) are ranked first, then environmental context, then logical recency. No embedding model, vector database or LLM is required for this baseline.

The integration boundary with the external Memoria.ia server remains intentionally open. Live.infinita now owns the concrete runtime event; a future adapter may export these episodes to Memoria.ia without making world simulation depend on that server being online.

## Test contract

`tests/test_nov_autonomous_scenario.py` and `tests/test_npc_episodic_memory.py` verify that:

1. building the runtime does not advance logical time;
2. only `nov` is enabled as an autonomous NPC;
3. the first logical tick chooses `energy`;
4. an authoritative plan or strategy execution is created;
5. Nov reaches the `shelter` region without external input;
6. an energy outcome is produced;
7. dynamic energy falls below its bootstrap value;
8. the energy experience is persisted as an episode in the same outcome cycle;
9. episode identity, strategy, target, logical tick and provenance are preserved;
10. rebuilding the runtime with the same persistent directory recalls the same episode;
11. duplicate `remember()` calls with the same episode id are idempotent;
12. recall is scoped per NPC and ranked deterministically by semantic/context match and recency;
13. day/night schedules and conditional reactions are installed exactly once across runtime rebuilds;
14. tick 12 changes the world to night with higher environmental danger;
15. the campfire lights on the same tick as night begins;
16. Nov's safety need rises when the night event raises danger;
17. tick 24 restores daytime and lower risk;
18. the campfire turns off when daytime returns;
19. safety trends down again after environmental danger drops;
20. recurring schedule cursors advance to ticks 36 and 48 rather than performing catch-up loops.

## Deployment

`deploy/autonomous-world.env.example` points to this bootstrap, but the systemd unit remains opt-in. Merely deploying the repository does not start autonomous simulation.

Activation must remain an explicit operational action after the current branch is validated and the server's persistent data directory is prepared.
