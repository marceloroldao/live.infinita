# 008DM — synchronized day/night illumination

## Implemented

The server attaches a validated read-only sky clock to spatial deliveries, even if cognitive terrain is unavailable. Its authority is the existing persisted simulation-clock.json. The renderer changes background, ambient light, fog color and directional lighting through dawn, day, dusk and night. Night retains visible fill lighting. Cycle length is 3,600,000 logical milliseconds (60 minutes of simulation time, not a promise about wall-clock elapsed time).

The renderer accepts integral finite clock fields, checks identity and rejects older ticks for the same world. It interpolates at most one authoritative tick and then freezes during outages. Paused snapshots stop interpolation. Reloaded clients use the same persisted tick instead of beginning a fresh cycle. No episodes, navigation counters, memory records, terrain samples or World State are written by this presentation feature. No shadows or volumetric clouds are added.

The 008DM installer also contains pending 008DL ground blending and the preceding recovery/navigation fixes. It updates native and web rendering plus spatial clock delivery, with backups and rollback, and restarts runtime and renderer. Existing clock files are not replaced. Apply as root:

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-day-night-cycle-008dm-root.sh
```

Wait for 008DM_OK and reload the browser. The installer is prepared; production is not updated merely by committing it.

## Remaining celestial-memory work

This is the timing and illumination stage. No star, Sun or Moon geometry is created and none is claimed to be linked to memory. The build explicitly reports memory_linked_celestial_bodies=false. Blue night fill is presentation lighting, not a stored Moon.

The currently inspected structural recent API supplies observation/event envelopes and a bounded window. It does not supply a complete per-nodule catalog with authoritative creation dates and payload sizes. Do not reinterpret observations, regions, recall routes or first-export timestamps as those missing fields.

The next contract needs world_id, stable nodule_id, original creation time with declared clock domain, actual payload byte count, provenance, and a verifiable retrieval receipt. Publish only numerical identity/size/time metadata, never raw user content. Decide whether the celestial projection is at the primitive structural-nodule level or at the persisted aggregate-memory level before claiming one star per nodule. Maintain original birth time across updates and rereads. A read or a repeated payload must not create a younger duplicate star.

Star direction should derive deterministically from identity. Distance increases with age relative to a stable world epoch; payload size sets intrinsic luminosity and apparent brightness decreases with distance. Visibility needs threshold hysteresis and gradual fade, with an explicit bounded display budget; no arbitrary substitution when a star is invisible. No telescope in this stage. Sun and Moon require persistent identified celestial entities linked to confirmed memory identities; their states follow the shared clock while their identities remain unchanged.

## Cloud and wind variation design

Separate physical state, cognitive projection and inference provenance. A bounded physical model should evolve temperature, humidity, pressure tendency and wind, with daytime heating, night cooling, moisture near water and altitude influence. Wind advects clouds; cloud formation/dissipation depends on moisture and temperature. Use a fixed simulation timestep and bounded rates, not rendering FPS or frame-level random changes.

A recovered inference can bias target wind or cloud formation only through a confidence-weighted bounded adjustment. Smooth actual state toward those targets. Record which recovered memories affected the adjustment. A forecast, a commanded weather change and the later measured outcome are distinct events; do not feed the forecast back as an independently observed outcome. Weather controlled by an inference also cannot by itself validate that forecast: evaluate prediction under held-out/uncontrolled intervals or a paired control with identical physical initial state.

The renderer should first use inexpensive cloud geometry and vegetation sway from the same wind vector; terrain and solid obstacles remain stable. These cloud/wind and inference features are design work, not implemented by 008DM.

## Validation

See DAY_NIGHT_CYCLE_RESULT_008DM.json for the exact automated results. Includes Python clock validation, Godot clock/lighting checks, transport signal delivery and wrong-world rejection, plus navigation/presentation regressions. Automated headless checks do not replace visual native/web inspection after installation. No claim of new Memoria.ia learning is made by this release.
