# 008EW — successive changes with complete movement-cost accounting

Parent code: a1deadb6a9950afc9a0ced25ab8852f3a3e068c3. Native policy is unchanged from deployed 008ER + 008ET + 008EU. This experiment changes no production service, configuration, database or live UI.

## Question and design

Does the current experience policy still yield net benefit when a previously useful pattern becomes expensive repeatedly, after paying for acquisition and readaptation?

The budget was fixed before execution: four initial acquisition tasks and four phases of twelve tasks each, with wall openings [-20, -110, 0, -20]. Each task has an actually executed perception-only control and a memory intervention with identical initial position, destination, wall geometry, capsule, speed and time step within the pair. Control disables pattern collection; both arms enable the same three physical navigation flags. Total: 52 control traversals and 52 memory traversals.

The existing real capsule physics scaffold is reused. The only change to its travel helper is retaining newly measured local outcomes when accepting recovered history. This matches the production collector's merge behavior. No experimental policy, global path planner, injected successful fact, teleport or geometry-specific preferred direction is used.

Four initial physical outcomes are stored via the production bridge in an isolated real SQLite Memoria.ia core with fallback disabled. Before each new phase, the core service is reopened, recall cache deleted and reingestion forbidden. RAM starts empty for each phase. The first decision uses cold recovered history. New local physical outcomes accumulate during its twelve trials, alongside that recovered history. The core is updated at phase boundaries, not after every trial.

The five cold recoveries contain 4, 16, 28, 40 and 52 actual physical facts. All final recovered facts exactly match their original physical records after removing observation IDs. Recommendation IDs were checked against the prior recovered snapshot. Memoria.ia stores and recovers the evidence; the native navigation scorer evaluates costs and selects directions.

## Observed phase results

Positive savings mean less movement than the matched perception control. Negative savings remain included.

| Phase | Opening z | Movement saving over all 12 trials | Simulated movement-time saving |
|---|---:|---:|---:|
| First change | -20 | -256.51 m | -76.8 s |
| Second change | -110 | +1,305.98 m | +392.0 s |
| Third change | 0 | -257.49 m | -77.4 s |
| Fourth change | -20 | 0.00 m | 0.0 s |
| All 48 post-training trials | | +791.98 m | +237.8 s |

In the first three phases, the first decision uses the previous recovered preference. Fresh exploration then tests both directions, and a RAM evidence preference starts on trial five. The fourth phase uses recovered evidence throughout, but its direction already matches perception: retrieval alone produces no additional benefit there.

All 104 actual traversals arrived, with zero collisions, watchdog rescues and global route builds. There were zero excluded/censored contacts and zero pending contacts at measured traversal ends. Thus this run includes all attempted travel, but does not exercise the physical failure penalty.

## Acquisition included

The four initial memory tasks cost 680.65 m / 204.2 simulated seconds. Performing the same four tasks with perception alone costs 937.30 m / 281.2 s.

**Matched-task comparison:** compare all 52 memory tasks with all 52 perception tasks, including acquisition and every adaptation trial.

| Total | Perception | Memory |
|---|---:|---:|
| Movement | 7,439.30 m | 6,390.66 m |
| Simulated movement time | 2,232.4 s | 1,917.6 s |

Net savings are **1,048.63 m / 314.8 s**, approximately **14.10%** of control movement. Initial bootstrap exploration already performs some acquisition tasks more cheaply; that is accounted for as exploration, not attributed to already learned choices.

**Conservative comparison:** charge every metre and second of memory acquisition as additional cost, then subtract it from savings across the 48 post-training tasks. The final net remains **+111.33 m / +33.6 s**. The balance becomes nonnegative on post-training trial 22 and remains nonnegative for the rest of this measured sequence. This is an observed prefix result, not an estimate for arbitrary future changes.

Two phases are worse than perception and one is equal. Reporting only the second phase would substantially overstate the benefit.

## Limits

This is a deterministic, isolated family of related flat-wall geometries. Repetitions are not independent statistical samples. Exact local sensor signatures can alias different passage locations. The result does not prove a causal production advantage, semantic generalization, learning of arbitrary terrain or future hunting performance.

Only physical movement cost is counted. Simulated time excludes SDK, CPU, database, network and storage overhead. Phase-boundary persistence differs from the production bridge's polling cadence. No collisions or stuck failures occurred, so failure-penalty effectiveness remains untested. Navigation remains the same production policy; no live claim or panel metric was added.

## Reproduction and evidence

Synchronize the isolated renderer project with current repository renderer files, then run:

```sh
/opt/live.infinita/.venv/bin/python tools/run_sequence_cost_008ew.py --project /home/etbra/008bz-godot-test --output-dir docs/SEQUENCE_COST_008EW
```

SEQUENCE_COST_008EW/ contains the full report, raw Godot logs and metrics for every phase, every original physical fact, all five recovered snapshots, and independent validation of totals and provenance. The runner rejects missing phases, invalid physics, lost local outcomes, unexpected recall counts, mismatched IDs or reingestion after reopen; it does not require positive savings.

The production renderer remained active with zero restarts and the original 2026-10-08 18:12:47 UTC start. No root installer is needed.

Next: add related corner/pocket obstacle fixtures and failure cases while preserving this matched comparison and counting every attempt. A later live comparison must separately measure production benefit before exposing it as a performance claim.
