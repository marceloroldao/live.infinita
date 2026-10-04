# 008CW — stable camera release after obstacle contact

## Observation and scope

The attached 11.96 s recording shows abrupt framing changes near a tree, including the character moving toward the bottom of the view. The native rollout log confirms 008CV installed. Code inspection identifies a contact instability: the collision-constrained camera pose was fed back into the nominal follower, which immediately tried to expand toward the normal trailing position each frame.

This patch addresses that camera contact mechanism. It does not establish that every visible oscillation in the recording has the same cause, change navigation choices, soften physical obstacles, modify walk speed, or write World State.

## Changes

- Keep nominal follow filtering separate from the final collision-constrained eye.
- Retraction to the current safe ray distance remains immediate.
- After contact, require 0.6 s of uninterrupted full clearance before extending.
- Extend at no more than 2 m/s; short alternating contact/clear gaps leave the arm shortened.
- Explicit camera resets reset contact history.
- Preserve nominal ground-height safety feedback and final ground clearance.

Tree/rock colliders and the existing heading filter remain in use. Sudden newly encountered obstructions can still require immediate safety retraction; terrain-induced camera height changes and real route reversals are separate concerns. This is the existing ray-based safety model, not a camera-volume sweep.

## Validation

The new regression tests immediate contraction, alternating gaps, maximum release speed, eventual full recovery, reset, nominal/output separation and consistency at 30/120 FPS. Existing camera tests include an actual physics wall, level horizon and ground clearance. Imported tree avoidance and bridge traversal remain in the publication suite.

## Installation

```bash
cd ~/live.infinita && git pull --ff-only && sudo bash deploy/apply-camera-contact-008cw-root.sh
```

Success marker: 008CW_OK. Log: /home/etbra/008cw-renderer-rollout.log. Existing backup/rollback and public health checks are retained. Confirm the actual live motion after installation; isolated tests are not a live visual acceptance test.

## Completed checks

All 18 publication Godot smokes passed on the final source. In the synthetic contact trace, 120 alternating blocked/clear samples produced zero arm-length oscillation after initial retraction. Two-second release distances were 5.8667 m at 30 FPS and 5.8167 m at 120 FPS, within the 0.08 m tolerance. Real wall camera safety, level horizon, ground clearance, imported nature collision/avoidance, bridge traversal and destination consistency passed. Bash syntax and git diff whitespace checks passed. Production is still on 008CV until the root installation; the user recording has not been visually revalidated against this new build.
