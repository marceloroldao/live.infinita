# 008EV — recovered experience with acquisition cost

Executed on 2026-10-08 against current native navigation code (008ER cost windows, 008ET contact turns and 008EU exit direction). Parent repository HEAD: 9554b9612b3be52de4ed1fe2d211faa8287d568a; deployed implementation: eb4b801ba432c259f9bc557683bd119ebe30729c. No production code, service, database or live configuration changed.

## Method

An actual CharacterBody3D capsule traverses the existing isolated flat-wall physics fixture. Both arms enable the same three navigation flags. Control disables the pattern collector; intervention accepts real recovered structural observations. No global path planner, teleport, rescue, synthetic successful outcome or hardcoded preferred side is used.

Acquisition consists of four native bootstrap traversals, with an additional matched control of four perception-only traversals at the same start, goal and wall opening. The four resulting physical facts are ingested via the production bridge into isolated real SQLite Memoria.ia with fallback disabled. The core is reopened, export cache deleted, and reingestion forbidden. Exactly four facts return with observation IDs.

Ten paired stable traversals use the same recovered snapshot and identical start/goal/geometry within each pair. These are deterministic repetitions, not independent statistical samples. The local state is deleted between arms; assessment trials cannot train later pairs. The passage then changes once, while the recovered snapshot remains frozen, to expose stale experience.

The current flags and physical validity were checked for all 30 measured traversals. All arrived, with zero collisions, rescues and global route builds. The first assessment contact in every intervention used recovered-pattern-evidence with nonempty real observation IDs and one changed initial decision.

## Results

| Measurement | Perception | Recovered experience |
|---|---:|---:|
| Four acquisition tasks, distance | 937.30 m | 680.65 m |
| Four acquisition tasks, simulated movement time | 281.2 s | 204.2 s |
| One stable reuse, distance | 237.94 m | 107.34 m |
| One stable reuse, simulated movement time | 71.4 s | 32.2 s |
| Changed passage with stale snapshot, distance | 107.34 m | 237.94 m |

Each stable reuse saves 130.60 m and 39.2 simulated seconds, approximately 54.89% of control distance.

**Conservative accounting:** charge all 680.65 m / 204.2 s of acquisition as additional cost. The sixth stable reuse repays that cost. Across ten measured reuses, savings minus full acquisition equal **625.32 m and 187.8 simulated seconds**.

**Matched-task accounting:** if Nov would perform the same four acquisition tasks anyway, acquisition already costs 256.65 m and 77.0 s less than doing them with perception only. Across acquisition plus ten stable reuses, the intervention saves 1,562.63 m and 469.0 s. This includes bootstrap exploration; it must not be described as four already learned decisions.

**Changed geometry:** the stale snapshot adds 130.60 m / 39.2 s compared with control. Repeated adaptation is intentionally outside this frozen-snapshot experiment; prior 008EQ/008ER experiments cover adaptive windows. This test makes no claim that the change has already been relearned.

## Scope and reproduction

This demonstrates a physical benefit of recovered evidence under the current policy in one isolated geometry, including acquisition movement cost. It does not establish a causal production benefit, broad transfer or statistical confidence. Exact sensor signatures can alias different wall openings. Time is simulated motion time, excluding CPU, SDK, database and network latency. No physical failure occurred, so error penalties are not tested here.

Run with the current isolated renderer project:

```sh
/opt/live.infinita/.venv/bin/python tools/run_acquisition_cost_008ev.py --project /home/etbra/008bz-godot-test --output-dir docs/ACQUISITION_COST_008EV
```

Artifacts: raw training and paired Godot logs, full metrics, four physical training facts, and recovered observation entries in ACQUISITION_COST_008EV/. Core storage is disposable and isolated; production credentials are not used. No root installer is required.

Next useful evaluation: carry adaptive memory across a sequence of changed passages, compare matched perception controls, and account for every failed, censored and exploratory attempt before extending to more obstacle shapes and animal encounters.
