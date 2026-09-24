# NPC Need Outcomes 001

## Goal

Close the deterministic feedback loop between internal NPC needs and completed semantic plans.

The cycle is:

`need dynamics -> utility -> proposal -> plan -> authoritative execution -> completed plan -> internal satisfaction`

Need satisfaction is internal compact state. It is not authoritative world replay and does not mutate the cold entity payload.

## Components

- `NpcNeedDynamics.satisfy(...)`
  - reduces one named need
  - clamps values to `[0, 1]`
  - requires a durable `outcome_id`
  - is idempotent for the same `outcome_id`

- `NpcNeedOutcomeProcessor`
  - scans current Plan Ledger records
  - only considers plans with `status=completed`
  - only considers intents carrying a supported `need`
  - applies satisfaction exactly once per completed plan
  - writes a separate append-only outcome audit log

## Default satisfaction

- safety: `0.50`
- energy: `0.40`
- social: `0.35`
- curiosity: `0.30`

These values are policy defaults and can be overridden by configuration.

## World Tick order

The feedback phase occurs after authoritative plan execution:

1. logical clock
2. scheduled events
3. conditional events
4. need dynamics
5. need utility / plan creation
6. plan replanning
7. arbitration
8. authoritative plan execution
9. need outcome satisfaction

This guarantees that merely creating or starting a plan never satisfies a need. Only a completed plan can do so.

## Invariants

- failed plans do not satisfy needs
- cancelled plans do not satisfy needs
- non-need plans are ignored
- processing the same completed plan twice has no additional effect
- satisfaction does not create a world event
- satisfaction does not alter authoritative replay
- satisfaction does not rewrite the cold entity payload

## Example

An NPC has `energy=0.91`. The need scheduler creates a rest plan. After the NPC actually reaches its configured rest target and the plan becomes `completed`, the outcome processor applies the configured energy satisfaction, for example `0.40`, resulting in `energy=0.51` before normal per-tick dynamics continue.
