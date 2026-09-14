# Atmosphere Presentation 001

Atmosphere is a renderer concern, not persistent world identity.

The World State may expose compact environmental descriptors under `environment`, while the Godot renderer resolves them into transient visual effects.

Supported presentation hints:

- `biome`: `forest`/`floresta` enables subtle mist and airborne motes.
- `weather`: `rain`/`chuva` enables rain; `dust`/`dry`/`poeira`/`seco` enables dust.
- `atmosphere_intensity`: normalized value from 0.0 to 1.0.

When these keys are absent, the showcase defaults to a light forest atmosphere and clear weather. The effects are deterministic functions of time and local presentation state; they are never written to replay, entity history, Memoria.ia, or the authoritative World State.

This preserves the architectural boundary:

`persistent meaning/state -> local slice -> presentation resolver -> transient atmosphere`

A large world therefore does not imply a large particle system. Only the currently rendered local slice receives presentation effects.
