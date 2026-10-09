# 008EY — one alternative fails, another reaches the goal

Parent repository: 98e6af8. Production navigation and deployment remain unchanged. The proposed policy exists only in tests/godot_failure_policy_008ey.gd and is activated only by the isolated assessment runner.

## Physical fixture and acquisition

A front wall has an open lower detour and an upper chamber. When the actual capsule occupies z >= 10 inside the upper chamber, a physical gate at z=5 closes behind it. The upper branch then has no exit. The gate trigger reads only occupied position; it does not inspect side, recommendation, memory, arm label or reward. The identical dynamic environment resets for every attempt.

This is an intentionally constructed deterministic one-way trap, not a claim about current live-map mechanics. Actual collision shapes, native swept movement, real local contour outcomes and the unchanged production watchdog are used. No teleport, global planner, shortened timeout or injected failure/success is used.

Eight acquisition tasks use current production scoring, each with an actually executed perception control. Bootstrap explores both directions. The retained native evidence is **six stuck_recovery records on side +1 and two contour_completed records on side -1**. In this fixture the two completed contacts also complete their whole journeys.

All eight actual records enter an isolated real SQLite Memoria.ia via the production bridge, with fallback disabled. The core is reopened, recall cache removed and reingestion forbidden. Original and experimental cold assessments recover exactly the same eight facts and observation IDs. No new fact is substituted for an inconvenient outcome.

## A current-policy blockage

The current evaluator returns side_without_success if either direction has only failed samples. Therefore the measured failures block a preference even though the alternative has two measured successes. After the four initial bootstrap facts, the collector stops bootstrapping this context and falls back to the default direction.

The cold current-policy journey again enters the trap and fails after **398.00 m / 119.4 simulated seconds**. Memory retrieval is correct; the rule consuming the evidence is too conservative in this particular mixed success/failure case.

## Isolated candidate

The experimental policy retains every original record and changes only the side_without_success branch:

1. Require exactly one direction with at least two actual successful local outcomes.
2. Require the existing minimum alternative samples and a score advantage above the existing 20% margin.
3. Recommend that direction using its real recovered observation IDs.
4. Abstain if both directions lack repeated success or the score evidence is weak.

It uses no absolute coordinates, geometry label, permanent ban or predetermined numeric direction. Error penalty remains 20 cost units. The rule is not installed in production.

The same cold history now selects the lower route, never closes the trap gate, and reaches the destination in **70.39 m / 21.1 simulated seconds**, with one verified core-caused change of initial direction.

## Diagnostic ablations

The physical environment is identical in every row.

| Cold arm | Evidence | Result | Movement | Simulated time |
|---|---|---|---:|---:|
| Current policy | Same eight recovered facts | Stuck | 398.00 m | 119.4 s |
| Experimental policy | Same eight recovered facts | Arrived | 70.39 m | 21.1 s |
| Experimental, negative evidence removed | Only the two real successful facts | Stuck | 398.00 m | 119.4 s |
| Experimental, numerical error component set to zero | Same eight recovered facts | Arrived | 70.39 m | 21.1 s |

The positive-only ablation filters a copy of the recovered snapshot solely for assessment; it neither changes the core nor creates or modifies any observation. With failures removed, the unexplored direction lacks samples and bootstrap tests it again. The body falls into the trap.

The zero-penalty ablation changes the explicit error component only in the experimental mixed-success/failure branch. The bad-side score becomes 100 instead of 120. Measured movement cost alone still supplies enough margin, so the body still succeeds.

**Conclusion:** in this fixture, retaining failed evidence and fixing the rule that blocks its use improves the held-out physical outcome. The numerical penalty of 20 is not necessary for that outcome here. We cannot attribute the gain specifically to the penalty weight.

## All attempt costs and validation

The original acquisition is shared, not reexecuted or counted as independent data for the candidate. The two alternative nine-task budgets below each charge the same eight current-policy acquisition attempts plus their respective cold intervention.

| Nine-task budget | Arrivals | Failures | Movement | Simulated time |
|---|---:|---:|---:|---:|
| Perception controls | 0 | 9 | 3,582.00 m | 1,074.6 s |
| Current-policy acquisition + current cold memory | 2 | 7 | 2,926.77 m | 878.0 s |
| Same acquisition + experimental cold memory | 3 | 6 | 2,599.16 m | 779.7 s |

Most acquisition attempts still fail. These totals are incomplete-task costs, not a completed-route efficiency percentage, broad learning gain or proof of amortization. The two ablation trajectories are additional diagnostic effort, fully archived separately from the primary matched budget.

Actual executions total **22 trajectories: 4 arrivals and 18 physical watchdog failures**. Zero collisions, global route builds, excluded contacts or pending contacts; no test-budget censoring. Six negative and two positive facts are durable. Cold assessment outcomes are archived but not ingested as new core history.

An additional contract check uses prior actual recovered corner, symmetric U and closed-enclosure records. All three existing decisions remain exactly unchanged. A subset with only one real success abstains, and disabled policy abstains. No synthetic outcome is ingested by these checks.

## Limits and next implementation

This is one constructed dynamic physical fixture. Deterministic repetitions are not independent statistical samples. Local sensor signatures can alias different situations, and local contour completion is not universally equivalent to whole-journey success. The candidate has not been validated as a production rollout, in mirrored traps, across later environment changes or as an online acquisition policy from empty memory.

Memoria.ia stores and returns verified history; the native scorer decides how to use it. Movement time excludes SDK, CPU, database, network and storage overhead. No live panel or production claim changes.

Production renderer remains active, NRestarts=0, with its 2026-10-08 18:12:47 UTC start. No root installer is provided at this experimental stage.

Next: validate this generic rule under changing and mirrored conditions, then integrate behind a reversible native flag with the full regression suite before a live rollout.

## Reproduction

Synchronize the isolated renderer with current repository renderer code, then run:

```sh
/opt/live.infinita/.venv/bin/python tools/run_asymmetric_failure_008ey.py --output-dir docs/ASYMMETRIC_FAILURE_008EY
/opt/live.infinita/.venv/bin/python tools/run_asymmetric_failure_008ey.py --experimental-assessment --output-dir docs/ASYMMETRIC_FAILURE_008EY
/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64 --headless --audio-driver Dummy --path /home/etbra/008bz-godot-test --script /home/etbra/live.infinita/tests/godot_failure_policy_contract_008ey.gd -- --offline-tour
```

ASYMMETRIC_FAILURE_008EY/ archives both raw executions, all original facts, both exact recovered snapshots, complete primary and diagnostic costs, independent physical/provenance validation and the contract execution output.
