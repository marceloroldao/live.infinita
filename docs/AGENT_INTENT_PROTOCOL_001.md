# Agent Intent Protocol 001

## Goal

Agents propose semantic intentions instead of low-level world mutations.

An intent is descriptive:

- `move_to_entity`
- `move_to_position`
- `establish_relation`
- `clear_relation`
- `set_environment`
- `transfer_possession`

The deterministic `AgentIntentResolver` translates an intent into canonical
operations. Translation is not authorization and does not mutate world state.

## Flow

```text
agent / Memoria.ia / director
        |
        v
semantic intent
        |
        v
Proposal Ledger (proposed)
        |
        v
explicit approval
        |
        v
AgentIntentResolver
        |
        v
canonical operations
        |
        v
Mutation Gate
   | rejected          | accepted
   v                   v
Proposal rejected   Mutation Decision
                       |
                       v
                 Cold World Engine
                       |
                       v
                  World Event
                       |
                       v
Proposal committed
```

A committed proposal must link both `mutation_decision_id` and
`world_event_id`.

## Authority remains separate from semantics

A valid semantic intent can still be rejected.

Example: an `entity_agent` representing `npc` may propose
`transfer_possession`, but resolution touches the object and recipient. Mutation
Gate therefore rejects direct self-authorization. A world-authorized principal
or operator approval is required.

Similarly, `set_environment` resolves deterministically but requires authority
that may execute `set_world`.

## Determinism

Resolution uses the authoritative cold store as its read source. The same intent
against the same entity state resolves to the same canonical operations.

The resolver never:

- calls an LLM;
- mutates the cold store;
- bypasses Proposal Ledger;
- grants authority;
- commits world events.

## V1 examples

```json
{"intent":"move_to_entity","actor_entity_id":"nov","target_entity_id":"bridge"}
```

resolves to a canonical `move` using the bridge's authoritative position and
region.

```json
{"intent":"set_environment","key":"weather","value":"rain"}
```

resolves to `set_world environment.weather=rain`, then Mutation Gate decides
whether the principal has sufficient authority.

```json
{"intent":"transfer_possession","actor_entity_id":"npc","object_entity_id":"gift","recipient_entity_id":"nov"}
```

resolves to ownership state + relation operations; policy still decides whether
that actor may cause them.

## Architectural consequence

Agents express goals. Deterministic infrastructure decides representation,
policy decides authority, and only the authoritative engine changes the world.
This reduces direct write power for probabilistic agents while retaining a clear
semantic layer for autonomous behavior.
