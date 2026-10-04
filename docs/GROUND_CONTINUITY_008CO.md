# 008CO — shared consolidated ground

Terrain remains inference-derived. Each sampled world coordinate is consolidated once per renderer session and shared by tiles, feet, camera, vegetation and trails. Unsampled coordinates use the latest proposal. This prevents inconsistent shared edges after inference updates and tile eviction.

Existing samples remain fixed for the entire session, not just within 45 m. Cache resets on renderer restart; it is not durable World State. Reachable routes, dynamic lake classification and independent massif visuals are not solved by this patch. Projection is not confirmation of its source inference.

Regression: changed inference between neighboring builds; shared border vertices; tile rebuild; visible/sensed surface agreement; floor stability. Publication also runs existing traversal and navigation checks.

Installer: deploy/apply-ground-continuity-008co-root.sh. Success marker: 008CO_OK.
