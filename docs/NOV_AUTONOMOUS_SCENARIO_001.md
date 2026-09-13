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
  -> later ticks may generate a different goal, such as curiosity toward deep_forest
```

The test does not require Nov to remain at the shelter forever. Once the energy outcome is applied, a later need is allowed to become dominant and create another goal. The invariant is the causal sequence: energy goal first, shelter visited, energy outcome applied, need reduced.

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

## Test contract

`tests/test_nov_autonomous_scenario.py` verifies that:

1. building the runtime does not advance logical time;
2. only `nov` is enabled as an autonomous NPC;
3. the first logical tick chooses `energy`;
4. an authoritative plan or strategy execution is created;
5. Nov reaches the `shelter` region without external input;
6. an energy outcome is produced;
7. dynamic energy falls below its bootstrap value;
8. day/night schedules and conditional reactions are installed exactly once across runtime rebuilds;
9. tick 12 changes the world to night with higher environmental danger;
10. the campfire lights on the same tick as night begins;
11. Nov's safety need rises when the night event raises danger;
12. tick 24 restores daytime and lower risk;
13. the campfire turns off when daytime returns;
14. safety trends down again after environmental danger drops;
15. recurring schedule cursors advance to ticks 36 and 48 rather than performing catch-up loops.

## Deployment

`deploy/autonomous-world.env.example` points to this bootstrap, but the systemd unit remains opt-in. Merely deploying the repository does not start autonomous simulation.

Activation must remain an explicit operational action after the current branch is validated and the server's persistent data directory is prepared.
