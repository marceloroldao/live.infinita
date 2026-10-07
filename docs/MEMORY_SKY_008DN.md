# 008DN — confirmed aggregate-memory sky

## Scope and interpretation

Each initial star represents one actual persisted aggregate Nov experience record in the local Memoria.ia incremental external-episode store. Its memory_id is the durable receipt state_id (external-episode:<record_key>), and its payload_sha256 and byte count refer to the complete canonical stored source payload. Export validates content checksum, identity, schema, world, actor and logical-tick provenance. Nothing is exported from unconfirmed renderer RAM.

This is an aggregate-memory projection, not the complete catalog of primitive structural/symbol nodules. The original experience logical tick provides the time basis. It is not presented as the unknown wall-clock time of disk insertion. No first-export timestamp substitutes for that time. Repeated reads/restarts preserve identity, original tick and payload size.

The bounded query scans up to 8192 recent records and displays the brightest 256 in that subset. It does not claim to show all memories or all primitive nodes. Export includes the total aggregate count and scanned count. Raw experience text/context/payload is never sent to the browser; only identity, checksum and numerical metadata are delivered.

## Visual distance and luminosity

Age in logical hours = max(0,current_tick - experience_tick) * tick_duration_ms / 3600000.
Projected distance = 1 + log(1 + age_hours).
Intrinsic luminosity = log(1 + payload_bytes) / 8.
Apparent brightness = min(1,intrinsic_luminosity / distance^2).

These are explicit visual mapping choices, not a claim of astronomical measurement. Direction is deterministic from SHA-256 of memory identity. The Godot sky renders on a camera-centered shell; the projected distance affects apparent luminosity rather than being interpreted as terrain distance in metres. Distant faint memories have no forced minimum visibility. Stars below brightness 0.009 remain hidden; eligible stars fade with night/day transitions. Existing-star refresh preserves its fade. The sky has no telescope. Budget replacement may remove a star when brighter candidates enter the bounded selection.

## Sun and Moon

Sun and Moon are persistent typed world definitions stored through the actual local structural API. Stable payloads include body identity, world, original birth tick, role and shared-clock orbit convention. A private registry is written before API submission so interrupted retries reuse the same definition. The core must acknowledge the exact event identity with durable storage or an idempotent duplicate; its duplicate path reconstructs and compares the existing stored envelope. No successful acknowledgment means no new sky projection is published.

These are authored world entities, not evidence that Nov learned astronomy. They use a dedicated hierarchy and source_kind, with chronological_episode=false and no World State or navigation selection authority. Their definition is not reinserted as a new record every frame or cycle. The repeated timer submissions verify the same two identities through idempotent core intake. Associated dynamic positions live in the rendering projection driven by the persistent clock; their memory payload is immutable.

The Sun and Moon are visible geometry in opposite positions of a simple daily orbit. The Moon is visually full in this first release; a lunar phase calendar, gravity and detailed astronomy are not implemented. Light direction now follows the same celestial geometry. Nighttime fill lighting remains visible for the live.

## Delivery and installation

A low-priority oneshot service plus 20-second timer reads local memory and publishes sky.json atomically with mode 0644 set before rename. It does not export secrets or raw user content. The spatial broadcast also refreshes on sky-file changes while the world is paused. World spatial delivery includes only a fresh same-world sky projection; renderer verifies schema, identity, freshness, bounds and confirmation flags. Missing/invalid data does not fabricate celestial bodies. Already shown data expires after 180 seconds without refresh. The service uses the existing credential file for localhost API access; credentials never go to Godot.

```bash
sudo bash /home/etbra/live.infinita/deploy/apply-memory-sky-008dn-root.sh
```

Wait for 008DN_OK and reload the browser. The installer includes 008DM and earlier ground/recovery fixes, exports web, installs native/runtime code, starts the sky service and timer, checks the two confirmed bodies and then verifies the public build. Backups and rollback restore previous runtime, rendering, service units and sky projection. Confirmed memory records and the retry registry are intentionally retained if rollout fails; deleting knowledge is not a rollback action.

Production is not changed merely by preparing or committing this release. Root installation and subsequent native/browser visual inspection remain required.

## Validation and remaining work

MEMORY_SKY_RESULT_008DN.json records exact results. Python checks include content integrity, freshness, world mismatch, original-time preservation, payload brightness mapping, and corrupt-data preservation of the previous file. Real installed V2 SDK tests use isolated SQLite stores: Sun/Moon API acknowledgments, repeated submissions, reopening and retrieval retain exactly two identities. A genuine IncrementalExternalEpisodeStore accepts a typed observation, emits a durable receipt, deduplicates its retry, reopens, and yields a star whose identity/hash/size match that receipt.

Godot checks cover deterministic directions, validated catalog acceptance, invalid/unconfirmed/stale/NaN rejection, fade continuity, day/night star visibility and opposite Sun/Moon visibility, plus navigation/terrain/camera regressions. Headless MultiMesh GPU readback is not used as visual proof. Native/browser pixel inspection after installation is still pending.

A full primitive-node catalog with authoritative node-creation time and payload attribution is still a separate contract. Clouds, physical wind, vegetation response, inference influence and controlled forecasting evaluation remain subsequent work. This release changes the representation of confirmed memories and world entities; it makes no new claim of learned navigation or weather inference.
