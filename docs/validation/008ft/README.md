# 008FT — Brake before sharp turns

Regression introduced by horizontal inertia: a high-speed capsule seeking a short sideways waypoint could accumulate more than one full rotation before entering the arrival tolerance. The previous response limited acceleration but retained full desired speed on sharp direction changes.

The response now scales desired speed by forward alignment when speed exceeds 0.3 m/s. A perpendicular or reversing target first requests braking; acceleration resumes towards the new direction once the old momentum has settled. Swept collision, gravity, navigation choices, camera, and stored history are preserved.

A differential test runs the same short-turn scenarios against the previous committed response and the new response at 15/30/60 FPS. The previous response failed six no-full-orbit checks. The new tests also exercise the actual native capsule with both inertia and gravity active.

The earlier inertia fixture now starts its corner check at 4 m/s: after the initial 0.9 m/s acceleration step, stopping within a frame under a 24 m/s² braking limit is physically valid, so a residual-momentum assertion must start above that stopping threshold.

Deployment: deploy/apply-nov-turn-braking-008ft-root.sh. Backs up the response and web build, runs export checks, installs the new response, restarts the renderer, verifies native health and the public source commit, and promotes the public build. Learning history is retained.

Validation: 58/58 export-suite checks passed with gravity and inertia enabled. Turn regression: 20 checks, 0 failures, including native capsule execution. The previous committed response failed 6/18 turn checks. Shell syntax and whitespace checks passed. Production installation is pending.
