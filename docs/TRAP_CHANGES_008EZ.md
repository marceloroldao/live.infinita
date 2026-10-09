# 008EZ — mirrored acquisition and repeated changes after cold recovery

Parent repository: d020af2. The candidate is still tests/godot_failure_policy_008ey.gd; production scoring, services, database and live UI are unchanged.

## Predeclared physical sequence

The 008EY one-way trap is mirrored by an environment parameter. The gate closes only when the actual capsule occupies the chamber; the scoring policy never reads the parameter. Initial position, destination, real collision shapes, movement, native collector, time step and watchdog are otherwise unchanged.

The sequence is fixed before execution:

1. Start with empty memory and the lower chamber trapping direction -1; eight paired acquisition tasks.
2. Reopen the real core, delete recall cache and execute one mirrored cold pair.
3. Move the trap to direction +1; twelve paired tasks.
4. Move it back to direction -1; twelve paired tasks.
5. Move it again to direction +1; twelve paired tasks.
6. Reopen the core once more and execute one final cold pair.

Total budget: **46 actually executed perception controls and 46 candidate-memory tasks**. Every initial exploration, failed trajectory, adaptation attempt and cold validation is included. Controls disable the pattern collector; both arms use the same production physical navigation flags. Legacy route memory is disabled.

A single world ID and relative sensor-context scheme persist across all stages. No evidence is deleted when the environment changes. Each stage starts with empty local RAM; recovered core history merges with fresh local outcomes during that stage. The actual new facts are ingested at each boundary, then the SQLite core service is reopened and export cache removed. Reingestion during cold recovery is forbidden.

This is a constructed deterministic physical fixture, not a description of deployed live trap mechanics.

## Results

| Stage | Trapping side | Control arrivals | Candidate arrivals | Control movement | Candidate movement |
|---|---:|---:|---:|---:|---:|
| Mirrored acquisition | -1 | 8/8 | 6/8 | 563.09 m | 1,218.32 m |
| Mirrored cold pair | -1 | 1/1 | 1/1 | 70.39 m | 70.39 m |
| First reversal | +1 | 0/12 | 10/12 | 4,776.00 m | 1,499.86 m |
| Second reversal | -1 | 12/12 | 10/12 | 844.64 m | 1,499.86 m |
| Third reversal | +1 | 0/12 | 10/12 | 4,776.00 m | 1,499.86 m |
| Final cold pair | +1 | 0/1 | 1/1 | 398.00 m | 70.39 m |
| All matched tasks | | **21/46** | **38/46** | **11,428.11 m** | **5,858.68 m** |

**Mirroring:** after real exploration, the candidate recommends direction +1 with actual recovered observation IDs. This is opposite to the -1 preference learned in 008EY. It matches perception in this mirrored cold case, so recovery alone is not counted as an added gain. Initial exploration has two failed attempts and costs 655.23 m / 196.6 simulated seconds more than controls.

**Each reversal:** the first cold decision uses the old recovered preference and enters the now-dangerous branch. The measured failure activates the existing cost-shift exploration window. Trials two through four supply fresh evidence on both alternatives. Each phase has two genuine stuck failures; from trial five onward all eight remaining candidate tasks choose the new safe side and arrive. Preferred directions therefore alternate -1, +1, -1 rather than remaining fixed or permanently banning a formerly failed side.

**Adverse phase:** the second reversal's control already selects the safe direction. Candidate adaptation then performs worse: two failed attempts, 655.23 m and 196.6 s extra. This cost, as well as initial acquisition cost, remains in the total.

**Final restart:** after recovering all 45 prior physical facts into empty local RAM, the candidate selects direction -1 using verified core evidence and arrives in 70.39 m / 21.1 s. Perception fails after 398.00 m / 119.4 s. The final outcome is also persisted, bringing total real facts to 46.

Aggregate simulated movement time is 3,428.1 s for controls and 1,757.0 s for the candidate. These are budgets containing failed tasks; their raw movement difference is not a completed-route efficiency percentage. Completion and failure counts are reported first.

## Data and checks

Six exact cold recoveries contain **8, 9, 21, 33, 45 and 46** actual native outcomes. Final recovered facts match all original physical records exactly after removing observation IDs. No fallback, production credentials, invented successful event or discarded failure is used.

All **92 physical trajectories** are archived: 59 arrivals and 33 real watchdog failures. These failures comprise 25 control failures and 8 candidate failures. Zero collisions, global route builds, time-budget censoring, excluded contacts or pending contacts at termination.

Independent validation checks body-triggered gate positions in both orientations, all three native flags in every arm, every raw cost total, distinct fact IDs, equality after recovery, the mirrored +1 preference, the three trial-five transitions, and the final corrected -1 core preference. The runner also checks recommendation IDs against the exact prior recovered snapshot and verifies accumulation of new local outcomes.

## Scope and next integration

This shows that the isolated candidate can acquire either directional preference, revise it after repeated related physical changes, preserve all history and recover the revised preference after restart. It does not establish semantic generalization, arbitrary obstacle mastery or a production benefit.

Perception is the comparison in this sequence; there is no current-policy memory arm. 008EY separately measured the old guard against the candidate on one fixed trap. Therefore the present totals must not be described as an overall percentage improvement over deployed memory navigation.

Repetitions are deterministic, not independent statistical samples. Relative signatures alias the changed environments; cost windows respond after failure rather than predict an unseen reversal in advance. Persistence happens at stage boundaries, unlike the production bridge's polling cadence. Simulated time excludes CPU, SDK, database, network and storage overhead.

No installer or production flag is introduced here. Production renderer remains active with zero restarts and its 2026-10-08 18:12:47 UTC start.

Next integration: add the generic successful-alternative rule behind a reversible native flag, verify both enabled and disabled regression suites, and prepare the root rollout while preserving old facts. A production performance claim still requires live paired evidence.

## Reproduction

Run from the repository with a current isolated renderer project:

```sh
/opt/live.infinita/.venv/bin/python tools/run_trap_changes_008ez.py --project /home/etbra/008bz-godot-test --output-dir docs/TRAP_CHANGES_008EZ
```

TRAP_CHANGES_008EZ/ contains raw logs, raw run metrics, every actual per-stage native fact, six recovered snapshots, the complete report and independent validation.
