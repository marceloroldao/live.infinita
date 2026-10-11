# 008FV — Presentation follows physical support

The previous visual selected walking or idle using horizontal speed alone. During gravitational motion the physical body stops horizontal movement, so a falling NOV appeared idle. The existing gait already follows executed horizontal speed; it did not need a second speed controller.

The scene now supplies the ground response's actual airborne state to NovCharacterVisual. Airborne support selects fall, stops advancement of the walking phase, and smoothly blends the primitive body's arms, legs and torso into a fall pose. Heading remains based on executed horizontal motion. A vertical terrain correction with gravity disabled remains supported and cannot trigger a fall.

On the airborne-to-supported transition, presentation starts one landing pulse. Its duration is 0.24 seconds, with strength bounded by the peak observed downward speed divided by 8 m/s. The primitive upper body dips at most 0.055 m and leans slightly while settling. Repeated supported frames cannot restart the pulse; upward-only motion cannot create an impact. Capsule transforms, gravity, collision, world positions, learned routes and stored animal histories are unchanged by this presentation.

The added grounded argument defaults to true for existing callers. Diagnostics expose support, motion phase, landing blend and executed horizontal speed. Verified imported rigs use only semantic clips installed on their own skeleton: a missing fall clip pauses walking while airborne, then resumes the supported action. The primitive landing pose is not an imported rig animation or foot IK.

Deployment: deploy/apply-nov-airborne-presentation-008fv-root.sh. Requires the installed 008FU physics dependencies to match the source checkout, backs up the visual and preview scene plus the public build, runs the export suite, installs the two presentation files, restarts the renderer and verifies current health, all three physics flags and the public build commit. Existing native feature drop-ins remain in effect. Rollback restores the prior files and public build.

The dedicated fixture checks fall and landing selection, stopped gait in air even with horizontal motion, bounded settlement at 15/30/60 FPS, repeated-support behavior, invalid inputs, missing verified rig clips, and the real scene driven by real gravity. It also checks that visual processing leaves the physical capsule unchanged. Production installation and live visual review remain pending.

Validation: 60/60 export-suite checks passed with inertia, gravity and terrain response enabled. Dedicated support-presentation fixture: 22 checks, 0 failures. All 11 required installed dependency files match the checkout, and both changed presentation files match the isolated tested project. Shell syntax and whitespace checks passed. Production installation is pending.
