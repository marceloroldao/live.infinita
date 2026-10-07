# Alternating local contour exploration — 008EF

When a physically observed contour continues for 64 m from contact without releasing a direct corridor, Nov reverses its tangent heading. Excursion limits then double (128, 256, ... m from original contact). Only committed physical positions advance the excursion. Existing physics checks, corridor release, goal resets and stuck watchdog remain active. The 64 m budget is a policy heuristic, not an inferred gap or shortest-path guarantee. Normal remains the goal-relative contact frame, not a measured surface normal.

The rule is shared by perception, RAM and core-recall comparisons. It creates no durable learning records or synthetic failures. No global route search or gap coordinates are supplied to the policy. Evidence exposes side switches and excursion budget.

## Controlled physical comparison

Start (-86,-80), goal (-68,-80), speed 4 m/s, dt 0.1; wall x=-80 spanning z=-180..180 with a 4 m gap. Each grid case uses an independent navigator and body. Times are simulated seconds.

| Gap offset from start | Previous contour | Alternating contour |
| --- | ---: | ---: |
| +20 m | 14.0 s | 14.0 s |
| -20 m | 158.4 s | 54.2 s |
| +50 m | 31.5 s | 31.5 s |
| -50 m | 158.4 s | 70.6 s |
| +80 m | 49.4 s | 101.2 s |
| -80 m | 158.4 s | 88.1 s |

All tested grid routes arrived without collisions or stuck-watchdog rescues. The +80 m case shows the cost of exploring the opposite side before a distant opening on the initial side. This finite fixture does not demonstrate generalization.

Changed-passage experiment: train at z=-30, close it and open z=-130. Previous contour: 527.95 m / 158.4 s, crossing beyond the wall end. New contour: 235.31 m / 70.6 s, crossing z=-128.882 inside the new gap. Perception, both stale-RAM copies and reopened real SQLite Memoria.ia recall have identical new distance/time. This demonstrates policy improvement, not memory advantage. Isolated transport explicitly bypasses production promotion eligibility; production state is untouched by testing.

## Validation and rollout

41 Godot regressions passed, including physical bidirectional fixtures, river/bridge safety, contour release, no frame-by-frame side switching, no forced motion without viable candidates, and stuck recovery. Both shell scripts pass bash -n. Logs and real-core comparison output accompany this document.

Run `sudo bash /home/etbra/apply-bidirectional-contour-008ef-root.sh`. Installer backs up native contour and web output, runs export checks, installs contour, restarts renderer and verifies fresh native state and public flags. On error it restores backups. Memory and wildlife state are preserved. The assistant has not run this root installer. Frozen v0.1.0 is unchanged.
