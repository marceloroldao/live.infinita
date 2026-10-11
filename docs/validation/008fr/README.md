# 008FR — Horizontal locomotion response

NOV already had scalar speed smoothing in the live scene. This change carries a horizontal velocity vector into actual capsule displacement, so turns and reversals have bounded acceleration rather than immediate direction changes.

- Acceleration: 18 m/s². Braking: 24 m/s². Existing live speed cap: 8 m/s.
- Final-goal distance controls braking; local waypoints cap displacement to prevent overshoot.
- Traversability validates the inertial displacement before the existing swept collision movement executes it.
- Rejected steps and collisions clear momentum. Recovery clears momentum before relocating the body.
- Recorded movement remains actual executed movement. No gravity, vertical inertia, capture, or world-state authority is added.
- Native activation: LIVE_INFINITA_NOV_INERTIAL_MOTION=1. Web activation: exported live_infinita/nov_inertial_motion=true.
- Low-level motion fixtures keep their explicit legacy mode unless they opt into inertia. The scene enables the configured response.

The traversal fixture now advances repeatedly until encountering the river or house; a single accelerating frame no longer implies contact with a distant obstacle.

Validation uses a separately imported temporary project because the checkout's old import cache contains root-owned files. The original asset import metadata is preserved.

Deployment uses deploy/apply-nov-inertial-motion-008fr-root.sh. The script checks unchanged animal dependencies, exports and tests the web scene, backs up native/web files and the renderer flag, activates the native response, verifies fresh publication and process environment, then promotes the public build. Rollback restores the previous renderer and web build without clearing learning history.

Final validation: 56/56 export-suite tests passed with native inertia enabled, including 12 inertia checks at 15, 30, and 60 FPS. Shell syntax and diff whitespace checks passed. Deployment is prepared; production activation has not been performed by this change.
