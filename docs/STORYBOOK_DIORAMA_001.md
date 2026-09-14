# Storybook diorama presentation

The renderer remains a projection of the received World State. The WebSocket,
interest updates, hot/warm/cold selection, narration policy, audio bridge and
Manager simulator contracts are unchanged. All new artwork is procedural Godot
geometry or a project-authored canvas shader; no external assets or licenses.

## Presentation

- `story_sky.gdshader`: continuous, statically dithered sky; Compatibility/Web GLSL.
- `diorama.gd`: three contours, distant woodland, bounded ground cover, river
  banks/highlights and village scenery anchored to up to two hot campfires.
  Village cottage silhouettes are decorative region motifs, not entities.
- `entity_visual.gd`: seeded tree silhouettes and wind, NOV idle/blink/scarf,
  velocity-based opposed limbs, arrival settling, fire glow and shelter/rest art.
- `atmosphere_overlay.gd`: bounded foreground foliage, leaves and night motes.
- `broadcast_overlay.gd`: above the world/effects, cached panels, temporary
  narration/audience cards and a small authoritative collective chapter label.

Sunlight interpolates over 18 seconds from the received period; intermediate
warmth does not advance the simulation clock. Numeric wind is clamped to 0..1,
with a weather-derived fallback. Local clocks never produce state mutations.

The director has a 22-pixel maximum pan, a 4-pixel/second speed limit, 6.5-second
focus and 14-second cooldown. Camera offsets affect drawing, not walking targets.
It can focus actual human movement/arrival, supported events and accepted chapters.
Depth uses entity feet instead of coarse bands. Portrait aspect is retained.

## Cost boundaries

Only `world.entities` becomes entity Nodes. Warm metadata stays in WarmPrefetch;
no cold-world scan, generated entities, new runtime, persistence or LLM authority.
The diorama adds one drawing Node and the UI one drawing Node, plus a sky rect.
Fixed scenery budgets: 74 grass tufts, 27 distant silhouettes, 25 river highlights,
12 bank stones, at most four village silhouettes, 22 foreground tufts, 18 corner
leaves and at most eight drifting leaves. Existing atmosphere intensity remains
clamped. Per-entity art has bounded loops and offscreen redraw is suppressed.
Eviction immediately removes the entity from the active map; at most 32 inert
visuals can finish a 0.35-second fade. Entry scale is 96%, avoiding large pops.

## Validation

Run the existing Python suite, JS checks and showcase preflight. On Windows,
three existing test modules require Unix `fcntl`; run the full suite on Linux CI.
The workflow retains the existing native Xvfb smoke and also checks every GDScript,
runs `tests/godot_presentation_smoke.gd` headless and with native rendering, rejects
Godot error logs and uploads four 720x1280 biome captures.

The new executable smoke covers immutable input, hot-only materialization, seeded
appearance, smooth lighting, stationary NOV under camera motion, bounded camera,
bounded/finite eviction and changing pixels without audience input. Fixtures live
only in the test runner, never in the production renderer.

Native command from the repository root:

```sh
godot --path apps/renderer-godot --resolution 720x1280 \
  --script ../../tests/godot_presentation_smoke.gd
```

Captures are written to `artifacts/godot/` (ignored locally). Public `/godot/`
requires the normal Web export and deployment after validation; source commits
alone do not replace the running deployment.
