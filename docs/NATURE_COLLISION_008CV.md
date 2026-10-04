# 008CV — nature collision follows generated transforms

## Reproduced failure

The 008CU live audit counted zero registered collisions, but that did not establish that visible nature blocked movement. The user observed Nov walking through trees and obstacles.

A new headless fixture loaded four real imported tree meshes and Rock_Medium_1.gltf, materialized each at a nonzero position and called the existing collision synchronizer. All five failed the capsule-blocking assertion. Diagnostic inspection found the StaticBody3D at (0, 0, 0) rather than the generated instance position. The synchronizer was reading MultiMesh instance transforms immediately after writes, obtaining stale render-side data.

## Correction

The collision synchronizer now requires the generator's CPU transform array. It places collision bodies directly from those transforms; no same-frame MultiMesh transform readback is used. Zero-item synchronization disables previously allocated bodies, and synchronization after relocation moves the collision to the new position.

Both perceptual tree layers and rocks pass the exact generated transforms. Previously decorative distant trunks, procedural undergrowth and midground shrub geometry now have bounded collision bodies too. Imported bushes are solid in the asset layer and tile decorations. Tall grass remains traversable. Tree trunks use cylinders, rocks and shrubs use bounding boxes: these are collision approximations, not exact triangles or canopy barriers.

Existing residency retains the geometry near Nov. This change does not relocate objects, weaken physics, modify the authoritative World State, or prove a new Memoria.ia learning gain.

## Validation

The new regression test checks all five imported meshes with a real physics capsule, collider coordinates, relocation, removal, and autonomous traversal around an imported tree. After correction, all five block; the detour reaches the opposite side with zero trunk overlaps and zero collision contacts. Existing bridge and destination tests remain publication requirements.

## Install

```bash
cd ~/live.infinita && git pull --ff-only && sudo bash deploy/apply-nature-collision-008cv-root.sh
```

Success marker: 008CV_OK. Rollout log: /home/etbra/008cv-renderer-rollout.log. Native and Web backup/rollback follow the established installer. Live behaviour requires verification after installation.

## Final validation

All 17 publication Godot smokes passed on the final source. The new physics fixture checks four imported tree meshes, a rock and a bush; relocation/removal of a collider; autonomous tree avoidance (reached=true, overlaps=0, collisions=0); and the live scene's distant trunk, midground, perceptual trunk and undergrowth collision wiring. The existing residency smoke now compares collider transforms with immutable CPU generation records rather than the same stale MultiMesh readback used by the old implementation: comparing two stale readings had concealed the defect. Bash syntax and git diff whitespace checks passed. Tests were isolated; production remains on 008CU until the root installer is run.
