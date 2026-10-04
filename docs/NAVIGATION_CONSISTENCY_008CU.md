# 008CU — perception, executable steps and dry destinations

The native 008CT audit observed blocked actions whose sensed candidate was allowed, including an empty failure reason. It also recorded a committed goal at (41.3356, -20.6937), inside the river away from the bridge: that exact destination cannot be reached under the existing physical rules.

## Changes

- Sense the complete proposed step with the same traversability check used at execution before sampling further ahead. Short 0.4 m samples can no longer conceal a rise above MAX_STEP_M over the proposed metre.
- Validate observed graph connections in consecutive steps of at most 1 m, matching the navigator's decision length. The existing 2 m graph must not apply an inconsistent total-rise rule.
- Record step_too_high explicitly for intermediate height rejection instead of inheriting an empty terrain classification reason.
- Before committing a new presentation destination, classify its ground surface. If unwalkable, search radii 1–16 m with 16 headings for a nearby nominally walkable position. Valid bridge destinations remain unchanged.
- If that bounded search fails, do not commit an impossible destination. Retry an unchanged rejected request after five seconds or immediately when the request changes.

This resolves a local renderer destination, with separate requested/resolved logs. It does not change the feed or authoritative World State. Surface classification does not prove global reachability or freedom from object collisions: those remain checked locally while planning and moving. Adjustment is a sampled nearby position, not a mathematically exact nearest point. Steep terrain, enclosed dry targets and bridges outside the observation window remain limitations.

## Validation

The new Godot smoke checks 60 slope/direction/step-length combinations: every perceived allowed candidate must pass whole-step validation. It separately checks excessive slope rejection, lateral escape, two consecutive executable metres, bounded dry destination adjustment, bridge preservation, committed resolved coordinates, unchanged input, and rejection of an entirely unwalkable neighbourhood.

The publication suite includes the physical bridge fixture and all existing navigation, camera, presentation, episode and memory smokes. Test results are reported after completion; production behaviour requires verification after installation.

## Installation

```bash
cd ~/live.infinita && git pull --ff-only && sudo bash deploy/apply-navigation-consistency-008cu-root.sh
```

Success marker: 008CU_OK. The installer backs up native and Web files, validates before export, restarts the renderer, verifies public flags and runtime health, and rolls back on failure. It logs to /home/etbra/008cu-renderer-rollout.log.

## Completed validation

All 16 publication Godot smokes passed on the final source. The additional physical fixture started at (18, -20), resolved requested river destination (41, -20) to dry destination (43, -20), crossed the actual project bridge, and reached it with zero collisions and zero water entries. The 60 slope comparisons passed. Bash syntax and git diff whitespace checks passed. Existing valid destination coordinates remain unchanged, including their feed height; only unwalkable destinations are adjusted. These isolated fixtures do not establish the outcome of every live route or a new Memoria.ia learning gain. Production still requires the root installer and subsequent live verification.
