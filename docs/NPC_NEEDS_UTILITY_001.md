# NPC Needs / Utility 001

## Goal

Allow NPCs to generate deterministic semantic goals from bounded internal state without granting them direct write access to the world.

## Current needs

The first policy supports four normalized need values in `entity.properties.needs`:

- `safety`
- `energy`
- `social`
- `curiosity`

Values are clamped to `[0, 1]`. A need must cross the configured threshold before it can generate a proposal.

## Deterministic utility

Each need has a policy weight:

- safety: 1000
- energy: 700
- social: 400
- curiosity: 200

The dominant need is selected by:

`utility = severity * policy_weight`

Ties are resolved deterministically by policy weight and stable need name.

## Intent generation

The NPC must provide an explicit target in its properties:

- `safety_target_entity_id`
- `rest_target_entity_id`
- `social_target_entity_id`
- `curiosity_target_entity_id`

The need scheduler generates a semantic `move_to_entity` intent only when the target exists. Missing targets are audited as `no_target`; no proposal or plan is created.

## Authority boundary

The need scheduler never mutates world state. Its pipeline is:

`NPC need -> Proposal Ledger -> deterministic approval policy -> PlanScheduler -> PlanArbiter -> Mutation Gate -> authoritative world event`

The plan principal remains an `entity_agent` scoped to the NPC itself. Every eventual plan step is still checked by Mutation Gate.

## Bounded evaluation

The scheduler receives an explicit list of NPC ids. It does not scan every entity in the persistent universe. A cooldown prevents the same unresolved need from generating a new proposal every logical tick.

## World Tick order

The current logical order is:

1. scheduled world events
2. conditional events
3. NPC needs / utility
4. plan replanning
5. per-actor priority arbitration
6. plan execution

This permits a high-priority safety need to create a plan and preempt a lower-priority social or curiosity plan in the same logical tick.

## Activation

The component is implemented but is not automatically enabled in the production server entrypoint yet. Runtime activation should happen only after the desired NPC roster and initial need/target properties are explicitly defined.
