# 008CC — Prevent terrain from covering NOV and the camera

The supplied video shows the view covered by a green ground face. Two rendering
inconsistencies were identified: feet/camera used an analytical height while the
local surface uses 8 m triangles, and a coarse horizon mesh also covered the
active local tiles. On a sharp slope either surface can lie above the position
computed for the walker and camera.

The analytical field now supplies mesh vertices; walk-height queries use the
same piecewise triangular interpolation as the visible local surface. Exact
vertices and grid edges have shortcuts to avoid unnecessary field evaluations.
The bridge walking-height adjustment remains in world_map_features.gd.

The horizon grid is split at the active tile rectangle and its interior omitted.
The detailed 3x3 surface is the only ground there. The coarse distant relief stays
outside that rectangle; active/cached tile budgets and world authority remain
unchanged.

Validation: 16 Python regressions passed. Five Godot smoke checks passed without
script or resource errors: ground alignment, locomotion, grounded camera,
physical traversal and live program overlays. The new regression covers the
existing analytical scale change near x=175, verifies surface interpolation and
checks that horizon triangles do not cover the active local area.

Deploy:
```bash
sudo bash /home/etbra/live.infinita/deploy/apply-ground-surface-008cc-root.sh
```

The rollout exports and tests the preview, installs presentation scripts,
restarts the renderer and updates /godot/. It retains the centered narrator,
audience/audio integration and hidden exploration toggle. Previous native/web
presentation files are restored if rollout fails.
