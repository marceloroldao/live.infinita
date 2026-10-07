# Native physical pattern feedback and core bridge — 008EH

The server renderer now attaches the relative pattern adapter to its actual episode and journey signals. Initial contact is captured only after a physically attempted action. A finished, eligible collision-free arrival or an executed journey ending in stuck recovery supplies outcome evidence. Goal changes, timeout interruptions, feed loss, shutdown, sensed-only rejection and journeys involving multiple distinct contour contacts are excluded. The last exclusion deliberately avoids ambiguous credit for an initial side.

Pattern cost covers actual movement from contact to termination, normalized by remaining distance measured at contact. No recovery teleport distance is added. Record identity combines a random renderer session and actual goal identity. Signals deliver feedback once, before reset/teleport. Predictions and recalled advice never become facts. Outcome records retain context/action/cost, not a route coordinate list.

Scope keys contain world identity and capsule/height/lookahead/contour profile. Changing world clears pending credit and isolates recommendations; the bounded native file can preserve older world outcomes. It retains at most 512 records atomically, loads validated retained records on restart, and makes no frame-frequency writes.

Initial exploration uses actual outcome counts: after the first measurement, at most four measured trials per previously unseen signature bootstrap two samples for each side. This is application exploration policy. All suggested sides must have physically viable local candidates; the existing corridor checks, expanding excursions, stuck rescue and goal limits remain in force. Exploration labels and learned preference counters are distinct. Excluded/censored runs grant no measured trial credit, so four outcomes is not a lifetime cap on interrupted attempts.

## Production bridge contract

New live-infinita-navigation-pattern timer runs 30 seconds after the previous invocation ends. Its restricted oneshot reads the native snapshot, filters current world and fixed physics profile, and sends at most four previously unconfirmed actual outcomes to the existing local structural API. Each row has an immutable attempt identity and content-derived event. SQLite receipts must match expected observation IDs and durable/duplicate flags.

It then reads actual API recent envelopes and validates exact event/provenance binding to each physical row before exporting private navigation-pattern-recall.json. ACKs or submitted rows are not substitutes for retrieval. Confirmed attempts are not resent on subsequent polls; partial intake resumes from confirmed checkpoints. Integral float side values from Godot JSON reloads are normalized before hashing.

Only core-recovered rows enter the recovered buffer. Same local/recovered attempt is merged once and annotated with its observation ID; contradictory or mismatched copies do not reinforce a local fact. Expired recall loses core attribution after 180 seconds while locally recorded facts remain usable. Invalid or unavailable core responses do not prevent local physical navigation.

The recent API window is bounded (64 requested, up to 100 returned); recovered export cache retains 512 verified rows. An older observation absent from both recent API window and cache cannot be reconstructed through this bridge yet. This is not full historical associative retrieval. Core associations remain deferred: application code defines signatures, scores costs/errors and chooses actions; the core stores and recovers structural evidence.

No navigation promotion bypass is required by this bridge: it has a new explicit eligibility contract for actual pattern outcomes. Such records are pattern outcome observations, not successful-route-step promotions. Isolated proof is not evidence that live performance has improved.

## End-to-end physical verification

The new physical fixture uses actual native motion constructor, actual episode callbacks, actual terminal journey signal, persistence save/load and automatic initial-side exploration. Four training journeys produced sides +1, -1, +1, -1 without a fixture assigning preferred sides. A later case changes both start and destination and translates the gap.

| Changed-position arm | Whole journey distance | Simulated time |
| --- | ---: | ---: |
| Same policy with patterns disabled | 234.572 m | 70.4 s |
| Retained actual native outcomes | 106.606 m | 32.0 s |
| Actual core-recovered outcomes with local buffer cleared | 106.606 m | 32.0 s |

All these journeys arrived with zero collisions, zero rescues and zero BFS/global route builds. Native contact-only costs were 232.315 m and 101.999 m during training; the reported table is whole-journey cost.

Production bridge code stored four actual collector rows in an isolated real SQLite core using pinned SDK dfd87c995b50c49b45a9d5dd4c43cce456983d4f. The store was reopened and the export cache deleted. Recovery rebuilt the same four rows with zero reingestion and unchanged store count. A subsequent actual native decision referenced recovered IDs, changed initial side and recorded its own real completion. Native core-change counter was one.

These are finite deterministic wall fixtures. The prior mirrored-gap experiment shows the same local signature can hide the opposite distant opening and initially worsen cost. Native online revision must be observed after rollout; arbitrary-world generalization and autonomous core policy learning are not established.

## Validation and install

43 Godot regressions passed, including collector credit, deduplication, world separation, TTL fallback, no sensed-only failure, ambiguous contact exclusion and existing camera/water/bridge/wildlife/telemetry checks. Nine Python component tests passed for real bridge contract mechanics, invalid facts, partial receipt failure, idempotency, world filtering, content binding and numeric compatibility. Their fabricated contract samples are isolated and never sent to production. End-to-end proof uses actual physical collector rows and real core.

Both shell scripts pass bash -n; systemd-analyze verify passed for the new service/timer (only unrelated installed XFS CPUAccounting deprecation warnings). Logs/results accompany this document.

Installer: sudo bash /home/etbra/apply-native-patterns-008eh-root.sh

It requires a clean git checkout and the active renderer, local core and animal timers. It backs up six native files, the Python bridge, timer/service definitions and public web output; runs export/regressions; installs and restarts; checks fresh native animal state, enabled pattern collector, bridge Result=success and public source/feature flags. On failure it restores those code/service/web backups, preserving observed memory and wildlife state.

The assistant has not executed the root installer. The live was checked before rollout: renderer active with public source 9f8d28d (008EF). The frozen v0.1.0 reference is unchanged. Native learning counters are recorded in the status file and NOV_PATTERN_DECISION / NOV_PATTERN_OUTCOME journal entries; this update does not add new live panel labels or claims.
