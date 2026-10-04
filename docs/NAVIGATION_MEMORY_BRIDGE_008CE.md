# 008CE — native navigation summaries in Memoria.ia local

008CD is deployed at /godot/ from commit 7e746f7; renderer active with NRestarts=0. A read-only copy of its actual saved navigation cfg was loaded by a separate Godot process: 31 blocked-passage entries and 677 successful route-step entries restored; a saved route was selected again. This verifies file-based restoration and reuse, not a production service restart.

The new Python bridge reads only the native renderer's ConfigFile. A strict, bounded parser accepts the current failures/routes format and refuses incomplete writes, invalid coordinates, excessive entries, duplicates and symlinks. It never evaluates GDScript. Browser user storage is not ingested.

Records become StructuralEvents in the local Memoria.ia API, with hierarchy live:navigation:<world>:nov:renderer. Failure counters and successful next steps remain marked as aggregate snapshots in Godot X/Z metres. These are not chronological episodes, authoritative World State moves, nor memories proven to influence Memoria.ia decisions. The cfg does not record original world IDs: world_id is explicitly the current runtime context, not a reconstructed historical identity.

Ingestion alternates failure/success candidates and sends at most two changed summaries per invocation. Event identities are content-derived; unchanged summaries do not reinforce memory. The local checkpoint advances only after the existing API acknowledgement matches the expected event ID, durable backend, deferred associations and exactly one stored/duplicate status. Retries are idempotent. Bounds: 4096 entries per source map, 2 MB source/checkpoint, counter 1..100. Evicted or saturated source entries cannot reconstruct earlier occurrence times. A timer runs every 30 seconds plus jitter, with low CPU/IO priority and localhost-only network access.

13 unit tests cover persistence acknowledgement rejection, partial-failure recovery, idempotence, changed counters/routes, parsing and limits. Separate integration with the installed Memoria.ia core in a temporary SQLite root accepted a real blocked-passage summary and successful-step summary through its FastAPI route, returned duplicates on replay, and restored both observations after reopening storage. Production API ingestion is checked by the installer.

Deployment:
sudo bash /home/etbra/live.infinita/deploy/apply-navigation-memory-bridge-008ce-root.sh

The script validates tests, backs up bridge/unit files, copies the bridge into /opt/live.infinita and validates its read-only preview as the service user there, then installs a separate service/timer, runs one ingestion and verifies its durable checkpoint. On failure it restores installation files and timer state. Acknowledged observations remain available and idempotent on retry. It does not restart or re-export the renderer, nor change the runtime writer. Success marker: 008CE_OK. Log: /home/etbra/008ce-rollout.log.

Next stage: retrieve matching navigation evidence from Memoria.ia and compare decisions with memory enabled/disabled. Receiving observations alone does not demonstrate a causal effect on choices.

Installer correction: the service user cannot traverse private /home/etbra (0750). The preview runs only from installed /opt paths inside the rollback scope. Home permissions remain unchanged. The failed initial installer stopped before changing production files or services.
