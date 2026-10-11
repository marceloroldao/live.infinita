# 008FS — Bounded gravity and terrain support

Adds gradual gravity-driven descent for small validated drops. The established terrain height remains the support reference; static obstacles are swept during vertical movement. This is an incremental ground response, not a full ballistic character controller.

- Gravity: 9.81 m/s²; fall speed capped at 8 m/s; integration step capped at 0.1 seconds.
- Downward floor following up to 0.08 m retains support; larger permitted drops fall gradually. Continuous slopes with grade up to 0.7 retain support independently of frame rate.
- Upward steps limited to 0.35 m in both traversal sensing and execution. Existing 1.25 m maximum descent stays enforced.
- Horizontal movement pauses while airborne and momentum clears. The live scene continues vertical integration even when the horizontal route has ended.
- Feet coordinates published by local motion match the actual capsule position. Landing clamps to the established floor; a swept static-body collision can stop descent above it.
- Explicit relocation clears falling state. No jumping, deep-cliff traversal, capture, damage, or weather forces are introduced.
- Pure vertical integration is tagged local_physics_gravity and does not create a navigation-memory decision or route-completion observation.
- Native activation: LIVE_INFINITA_NOV_GRAVITY=1. Web activation: exported live_infinita/nov_gravity=true.

Deployment uses deploy/apply-nov-gravity-008fs-root.sh with the previous inertia and contact-search flags retained. Native/web files and the new renderer flag are backed up for rollback; learning history is preserved.

Final validation: 57/57 export-suite tests passed on the final source with both inertia and gravity enabled. Gravity test: 33 checks, 0 failures, including physical descent, obstacle support, continuous slopes at 15/30/60 FPS, native live integration, and exported-settings activation. Shell syntax and whitespace checks passed. Production remains on 008FR until the deployment script is executed.
