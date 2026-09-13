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

This keeps the first autonomous cycle deterministic. The campfire remains present for future conditional events and alternative-strategy experiments, but is not initially an energy target.

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

## Test contract

`tests/test_nov_autonomous_scenario.py` verifies that:

1. building the runtime does not advance logical time;
2. only `nov` is enabled as an autonomous NPC;
3. the first logical tick chooses `energy`;
4. an authoritative plan or strategy execution is created;
5. Nov reaches the `shelter` region without external input;
6. an energy outcome is produced;
7. dynamic energy falls below its bootstrap value;
8. the clock advances only through explicit world ticks.

## Deployment

`deploy/autonomous-world.env.example` points to this bootstrap, but the systemd unit remains opt-in. Merely deploying the repository does not start autonomous simulation.

Activation must remain an explicit operational action after the current branch is validated and the server's persistent data directory is prepared.
