# NOV visual identity 001 — Quaternius / Godot 4

## Chosen packages

- Body: Quaternius Universal Base Characters, free **Standard** edition; regular female full-body humanoid.
- Motion source: Quaternius Universal Animation Library, free **Standard** edition; prefer non-root-motion Godot/Unreal GLB.
- License: CC0-1.0 (both).
- Author: https://quaternius.com/packs/universalbasecharacters.html
- Animation author page: https://quaternius.com/packs/universalanimationlibrary.html

Standard contains a subset of the full animation library; don't claim the
120+ Source clips are included in the free archive. No paid pack is needed.

This patch provides an independent presentation-only 3D character component,
importer, tests, and optional preview. The production 2D main scene remains
unchanged. Neither a generic placeholder nor a donor animation library is
evidence that Nov's final appearance/retargeting is complete.

## Import official Standard ZIP files

Download the free Standard ZIPs via the publisher's links. If the official
site rate-limits downloads, obtain them through its browser flow; never use
unverified third-party copies.

Run from the repository root:

    python3 tools/import_nov_character.py \
      --body-zip "/path/to/Universal Base Characters[Standard].zip" \
      --animations-zip "/path/to/Universal Animation Library[Standard].zip" \
      --dry-run

    python3 tools/import_nov_character.py \
      --body-zip "/path/to/Universal Base Characters[Standard].zip" \
      --animations-zip "/path/to/Universal Animation Library[Standard].zip"

    godot --headless --editor --quit --path apps/renderer-godot
    godot --path apps/renderer-godot res://nov_character_preview.tscn

The importer stages a regular female full-body glTF and its referenced
buffers/textures, plus one Godot/Unreal non-root-motion animation GLB.
The catalog at apps/renderer-godot/assets/quaternius/nov_character/catalog.json
records actual clip names, selected source paths and SHA-256 of both ZIPs.
It refuses ZIP path traversal and missing glTF dependencies.

If the publisher renames the files, review the new archive and adjust the
selection explicitly; don't silently change Nov's body type or skeleton.

The ZIPs, selected character binary and animation binary are NOT currently
in this repository. After the real vendor import succeeds, commit the
selected directory separately. No vendor download is required to test the
optional scene's placeholder mode.

## Cognitive/renderer contract

    Nov's needs/intent -> PlanScheduler -> Mutation Gate -> World State
                                                        |
                                                 presentation
                                                        |
                      NovVisual.apply_visual_intent(action, heading)

Supported action intents: idle, walk, run, interact. The visual component
cannot write positions, memory, world time, beliefs, or plans. Position must
always originate from the authoritative world (not animation root motion).

The importer INSPECTS the animation GLB, but does not retarget its tracks
automatically onto the selected character body. It records
retarget_verified=false. The Godot component refuses to play donor clips
unless they are actually installed and verified on the body skeleton. After
a real retarget and animation test, a future milestone can enable
AnimationTree/blending and set the verified flag.

## Tests

    python3 -m unittest -v tests.test_nov_visual_importer
    godot --headless --editor --quit --path apps/renderer-godot
    godot --headless --path apps/renderer-godot res://nov_character_preview.tscn --quit-after 2

The preview reports real model availability, uses an explicitly generic
placeholder otherwise, and may show already-vendored nature models.
