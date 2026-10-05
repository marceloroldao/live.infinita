# 008CX — successive local frontiers for distant passages

## Problem

The observed-route planner selected only endpoints closer to the committed goal. A long barrier can require movement away from the goal before a passage enters the 64 × 64 m observation window. Greedy fallback after an exploratory leg could immediately undo that leg.

## Changes

The existing physically probed graph remains bounded to 1089 nodes per local search, sliced across frames. If its closest-to-goal endpoint is already in the executed-position coverage and not within 3 m of the goal, the navigator selects a reachable fresh window boundary instead. A heading preference maintains an exploratory direction. If no reachable boundary continues that heading, the planner can reverse through the known corridor and retain that return direction until a fresh endpoint is reached.

Once exploratory heading is active, finishing a cached route continues local planning even if the short direct corridor appears clear. It must not immediately undo exploration by returning to greedy goal pursuit.

Coverage is at most 4096 coarse 8 m cells, recorded from actual current positions. It resets on a new committed route/goal. One visit does not prove that an entire cell has been inspected. This is temporary renderer search bookkeeping, not a global authoritative map or a new causal Memoria.ia recall claim. Every executed step still passes current physical validation. No river or bridge coordinates were added to the navigator.

Goal commitment now reassesses after 180 seconds without entering a new coarse cell, rather than expiring while novel exploration is advancing. Repeated visits to known cells do not renew that timer. A separate 900-second hard limit remains. Both timers use the existing clamped frame delta, not elapsed wall time. Coverage and deadline bookkeeping are bounded.

## Validation

The new physics fixture places the real project bridge initially 128 m from the observer in either direction, outside the initial local window. It checks arrival, actual frontier movement, reverse movement after the initially wrong direction, zero collisions, zero water entries and bounded coverage. It also checks lease renewal by new positions, stationary expiry, repeated-cell oscillation expiry and the hard deadline.

A first successful wrong-direction trial travelled approximately 1080.08 m in the flat 1024 m-wide fixture. This is evidence of finding a passage and recovering, not shortest-path performance. This fixture does not represent every cognitive terrain, vegetation configuration, narrow gap, dynamic obstacle or the entire 2048 m live world. Coarse coverage, the two-metre graph, local frontier heuristics and bounded deadlines can still fail to complete some routes. Live arrival must be verified after installation.

## Installation

```bash
cd ~/live.infinita && git pull --ff-only && sudo bash deploy/apply-frontier-routes-008cx-root.sh
```

Success marker: 008CX_OK. Rollout log: /home/etbra/008cx-renderer-rollout.log. Native/Web backup, rollback, publication smokes, public flags and runtime health verification remain in the installer.

## Completed validation

All 19 publication smoke logs completed with zero failures and no script/parse errors. Physical distant-bridge trials from z=-160 and z=96 reached their original destinations with zero collisions and zero water entries. Distances were approximately 1080.08 m and 440.08 m; the first used 960 return movement frames after choosing the initially wrong direction. An additional integrated goal-lease check kept the original committed goal through both entire physical traversals despite changed feed proposals, with no expiry. Stationary and repeated-two-cell movement expired after approximately 180 seconds without novelty; the 900-second total limit remained effective. Bash syntax and git diff whitespace checks passed. No production rollout or new causal persistent-memory gain is claimed by these isolated checks.
