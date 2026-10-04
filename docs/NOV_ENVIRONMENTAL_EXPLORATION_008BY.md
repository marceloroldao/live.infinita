# 008BY — Environmental preferences in NOV exploration

Idle crossings now consult the same stabilized regional environmental model
used by the renderer. A deterministic discomfort score combines temperature,
slope, snow, wetland membership, and vegetation density. A difference of at
least 0.12 can favor a more comfortable adjacent candidate.

Only existing topological neighbors are considered. The existing immediate
backtracking restriction remains. Every fourth crossing rotates through
available candidates independently of the comfort ranking, retaining exploration.
Need-driven or active plans take precedence and do not consult this adapter.
Missing or rejected projection data preserves topology-based exploration.

The model is regional, not an actual visibility or collision model. It does not
infer potable water, food, shelter availability, or bodily needs from affinities.
It reads the bounded projection file without querying Memoria.ia databases.
The scheduler and mutation gate retain all movement authority. The memory-derived
projection is advisory evidence, not a world writer or an autonomous decision maker.
The state ID, candidate scores, mode, and selected region are included in idle
results and persistent crossing intent metadata for diagnosis.

Validation: 67 tests covering environmental costs, deterministic preferences,
periodic exploration coverage for 2–5 candidates, missing/wrong-world evidence,
stabilized terrain, topology scope, need precedence, and existing runtime/scheduler
regressions. Installed predecessor files matched repository HEAD before rollout
preparation.

Deployment:
```bash
sudo bash /home/etbra/live.infinita/deploy/apply-environmental-exploration-008by-root.sh
```

The script checks the clean committed source and installed predecessor, runs
the tests, backs up changed runtime files, installs them, validates live evidence,
and restarts only the autonomous-world service. It checks clock advancement
and API health and restores previous files if installation or validation fails.
This does not require a Godot export: rendering assets remain at 008BX.
