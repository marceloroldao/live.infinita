# 008FU — Speed response to local terrain slope

NOV now uses the canonical ground geometry to adjust requested horizontal speed before inertial execution. A 0.5 m sample ahead follows the selected movement direction. The signed height difference divided by sample distance determines grade, clamped to [-0.7, 0.7] for this response. Grades within 0.03 keep the requested speed. Uphill speed factor is 1 / (1 + 2 * grade); downhill factor is 1 / (1 + 0.75 * abs(grade)).

At an 8 m/s base speed, flat terrain retains 8 m/s, a 20% uphill grade requests about 5.714 m/s, and the same descent requests about 6.957 m/s. These are tunable game movement limits, not measurements of human physiology. Acceleration, braking before sharp turns, collision sweeps, gravity, obstacle checks and the existing step limits still govern executed movement. A lower requested speed brakes through the existing inertial response. The slope sample never grants permission to cross an obstacle, water or a forbidden step.

The added terrain_motion diagnostic reports the sample grade, phase, speed factor, requested speed limit and actual executed horizontal speed. During pure gravitational motion, horizontal speed is zero and the phase is airborne or landed. Invalid geometry halts horizontal execution. The profile is session telemetry; it has no world write authority and supplies no metabolic expenditure, fatigue, material friction, learning reward or fabricated observation.

Activation: LIVE_INFINITA_NOV_TERRAIN_RESPONSE=1 for the native renderer; live_infinita/nov_terrain_response=true in the exported project. With the feature disabled, the previous movement behavior remains available.

Deployment: deploy/apply-nov-terrain-response-008fu-root.sh. It requires a clean checkout and matching previously installed physics and perception dependencies; backs up the native files, feature drop-in and public build; runs the export checks; installs the native response; verifies fresh renderer health, the feature environment and the public source commit. Its rollback restores the prior native files, feature setting and public build. Stored learning and animal histories are retained. Production installation remains pending until the user runs this script.

The dedicated fixture exercises directional samples, the small-grade dead zone, bounded response on steep samples, invalid samples, real capsule travel at 15/30/60 FPS, uphill/downhill physical support, executed-speed diagnostics, feature-off compatibility and exported scene activation. Results are recorded in the adjacent files after validation completes.

Validation: 59/59 export-suite checks passed with inertia, gravity and terrain response enabled. The first 12 checks were repeated successfully after finalizing diagnostic publication. Dedicated terrain fixture: 22 checks, 0 failures. Shell syntax and whitespace checks passed. Production installation is pending.
