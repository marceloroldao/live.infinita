# NPC Need Dynamics 001

## Goal

Evolve NPC internal needs from the logical Simulation Clock without tying behavior to renderer FPS or server wall-clock time.

The need dynamics state is intentionally separate from full cold entity payloads. This avoids rewriting a complete entity on every tick just because a scalar such as energy changed by a small amount.

## State

Each explicitly registered NPC can maintain compact normalized values in `[0, 1]`:

- `safety`
- `energy`
- `social`
- `curiosity`

Initial values may be seeded from `entity.properties.needs`. Subsequent values live in the compact `npc_need_state_v1` state file.

## Tick semantics

One call to `advance_tick(tick)` applies at most one dynamics step.

- Calling the same or an older tick is idempotent.
- A large tick jump after downtime does not replay missed dynamics ticks.
- The behavior follows the Live.infinita no-catch-up rule used by the Simulation Clock / Tick Driver.

## Default dynamics

Default per logical tick:

- safety: `-0.003`
- energy: `+0.002`
- social: `+0.0015`
- curiosity: `+0.001`

Context modifies those values deterministically:

- local/world `danger_level` raises the safety need;
- being in the same region as `rest_target_entity_id` lowers energy need;
- being in the same region as `social_target_entity_id` lowers social need;
- being in the same region as `curiosity_target_entity_id` lowers curiosity need.

All values are clamped to `[0, 1]`.

## Separation of responsibilities

`NpcNeedDynamics` only evolves compact internal state.

It does **not**:

- create plans;
- mutate authoritative world state;
- bypass Mutation Gate;
- scan the full world.

`NpcNeedScheduler` reads the dynamic state through `need_state_provider`, computes utility, and may propose a semantic intent. The usual Proposal Ledger → Planner → Plan Arbiter → Mutation Gate path remains unchanged.

## World Tick order

The intended logical order is:

1. scheduled world events;
2. conditional world events;
3. NPC need dynamics;
4. NPC need utility / proposal generation;
5. plan replanning;
6. plan arbitration;
7. authoritative plan execution.

This permits a need to cross a threshold and create a plan within the same logical tick, while preserving deterministic ordering.

## Scaling rule

The dynamics engine evaluates only explicitly registered NPC ids. It does not enumerate all cold entities. Full payloads are fetched only for those NPCs and their configured contextual targets.
