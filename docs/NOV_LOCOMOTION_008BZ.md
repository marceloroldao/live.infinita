# 008BZ — NOV walking and movement presentation

The live Godot view now treats received observer positions as presentation
targets. After the initial bind, the character accelerates toward the latest
target, turns through velocity changes, slows near arrival, and follows the
existing walking surface height. Initial binding and leaving local exploration
still place the visual at the authoritative position.

This is visual interpolation: no position, clock, intent, memory, or World State
is written. The displayed position may lag the latest received position during
movement. The existing local physics and collision path remains intact.

The primitive NOV visual now has opposite leg and arm swings, distance-driven
step phase, gradual pose settling, torso movement, breathing, and smooth relative
heading. Imported verified rig clips retain their AnimationPlayer path; this
change does not claim that donor skeleton retargeting has been completed.
Camera heading now responds to small frame steps instead of needing 35 cm per
frame, which previously prevented turns at higher frame rates.

Validation:
- 15 Python presentation/camera/walking regression tests passed.
- Godot locomotion smoke: 0 failures and no script/resource errors.
- Godot grounded presentation smoke: 0 failures and no script/resource errors.
- Godot physical traversal smoke: 0 failures and no script/resource errors.
- Godot tests used an isolated project and existing production asset imports;
  the running renderer was not used as the test process.

The exporter now checks locomotion and grounded-camera tests before publication.
Build metadata exposes nov_smooth_locomotion and nov_procedural_gait.

Deploy:
```bash
sudo bash /home/etbra/live.infinita/deploy/apply-nov-locomotion-008bz-root.sh
```

The rollout backs up the installed scripts and preview, exports and tests the
preview, installs two visual scripts, restarts the renderer, and checks public
metadata and API health. On failure it restores the previous visual files and
preview. Output is saved to /home/etbra/008bz-rollout.log.
