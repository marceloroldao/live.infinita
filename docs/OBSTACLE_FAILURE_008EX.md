# 008EX — corners, U pockets and actual stuck failures

Current native policy: 008ER cost windows + 008ET contact turns + 008EU exit direction, identical in both arms. Production code, configuration, renderer session and memory storage are unchanged.

## Fixed experiment

Three isolated real physics fixtures are measured separately:

- Corner: front wall plus one arm. Two viable initial contour directions have different travel costs.
- U pocket: front wall plus two equal arms. The capsule must retreat and go around; neither initial direction is cheaper.
- Closed enclosure: the U receives a back wall. Nov starts inside; the goal is outside. No physical exit exists.

Each case executes eight acquisition tasks with actual paired perception-only controls, followed by one paired cold-core task. The capsule, start, goal, obstacles, speed (4 m/s), step (0.1 s) and all three navigation flags match within each pair. Pattern collection is disabled in control. Legacy route memory is disabled in both arms. Each case has its own world/core to avoid mixing aliased sensor signatures across geometries.

The native watchdog observes real occupied positions with unchanged 30 s confined / 90 s no-new-area thresholds. A detected watchdog stop aborts the native journey as stuck_recovery; exhaustion of the 2500-step test budget would be interrupted and censored. No watchdog threshold is shortened, failed sample injected or successful exit fabricated. A detected failure stops the experiment's attempt; it does not teleport the body.

Eight actual native outcome facts per case are sent through the production bridge to an isolated real SQLite Memoria.ia core with fallback disabled. The core is reopened, exported recall cache removed, and reingestion forbidden. All eight facts return exactly unchanged, with real observation IDs. The cold navigation decision starts with empty local RAM and consumes this verified snapshot.

## Results including acquisition

All figures below count nine complete attempts per arm, including initial exploration and cold validation. Failed attempts remain counted.

| Case | Control arrivals | Memory arrivals | Control movement | Memory movement |
|---|---:|---:|---:|---:|
| Corner | 9/9 | 9/9 | 1,122.37 m | 742.12 m |
| U pocket | 9/9 | 9/9 | 1,717.20 m | 1,717.20 m |
| Closed enclosure | 0/9 | 0/9 | 6,235.20 m | 6,235.20 m |

**Corner:** net saving is 380.25 m / 114.1 simulated seconds across all nine tasks, about 33.88% of control distance. After cold core recovery, the actual initial direction changes using verified observation IDs: control travels 124.71 m and recovered evidence travels 70.39 m. All tasks arrive.

**Symmetric U:** no meaningful saving. The cold decision reason is insufficient_margin; the navigator abstains from a learned preference. Both cold trajectories are 190.80 m. Small aggregate floating-point differences are not improvement.

**Closed enclosure:** all eighteen measured journeys terminate via the actual repeated_area_no_goal_progress watchdog. Each cold arm travels 692.80 m, and total simulated time is 1,870.2 s per nine-task arm. These costs are not omitted and are not presented as successful performance. Neither memory nor control reaches the goal.

Across the whole matrix: **54 actual traversals, 36 arrivals, 18 real stuck failures**, zero collisions, zero global route builds, zero test-timeout censoring, zero excluded native contacts and zero pending contacts at termination.

## Actual error recording and penalty

The closed acquisition creates **eight native stuck_recovery facts**, with completion_basis stuck_recovery. All eight survive real core storage and cold recovery. The other two cases each store eight contour_completed facts: **24 distinct persisted facts total**. Each cold intervention produces one additional local validation outcome, archived in its raw run but not added to the isolated core.

On the closed cold decision, both alternatives contain real failed samples. The measured travel component saturates at 100 cost units; the existing error component adds 20, giving **score 120** for both directions. The runner and independent validation recompute this from recovered physical records. In this fixture it verifies that actual failures reach the current penalty path.

The cold reason is side_without_success, and the learned recommendation remains empty. This does **not** establish that the penalty causes better failure avoidance: both directions fail, and there is no counterfactual route that could succeed. The navigator also spends essentially the same time and distance as perception before detecting the impossible task. There is no demonstrated earlier-stop improvement.

## Scope

Evidence supports a current-policy benefit on the corner, sensible abstention on equal U costs, and durable recording/penalization of real stuck failures. It does not prove cross-geometry transfer, semantic understanding of a closed enclosure, arbitrary obstacle learning or a production/live benefit. Memoria.ia stores and returns history; the native scorer infers the preference.

These are deterministic fixtures, not independent statistical samples. Simulated movement time excludes CPU, SDK, database, network and storage overhead. Failure contacts and whole-journey completion are distinct concepts. We do not combine failed travel with completed tasks to claim a global percentage benefit.

## Reproduction

Synchronize the isolated renderer with current repository renderer files, then:

```sh
/opt/live.infinita/.venv/bin/python tools/run_obstacle_failure_008ex.py --project /home/etbra/008bz-godot-test --output-dir docs/OBSTACLE_FAILURE_008EX
```

OBSTACLE_FAILURE_008EX/ archives all raw logs, metrics, physical outcomes, recovered snapshots, the full report and independent validation. The runner saves raw evidence before rejecting contract errors; actual watchdog failures are permitted measured results, not discarded failed tests. Provenance, native flags, guarded movement and recovered failure scores are checked.

Production renderer stayed active, NRestarts=0, with its 2026-10-08 18:12:47 UTC start. No root installer is required.

Next experiment: an asymmetric physical obstacle where one choice truly fails and another completes, to determine whether the error penalty changes subsequent choices and improves completion/cost after accounting for failed acquisition.
