# 008CG — anticipate obstacles and use retrieved navigation evidence

008CF camera stabilization is deployed successfully. This release closes the navigation observation/recall loop: the existing service ingests changed native summaries, retrieves observations through the local Memoria.ia structural API and publishes a bounded recall snapshot. A cache retains up to 4096 API-confirmed entries beyond the latest 100-record retrieval window. It is not rebuilt from the renderer cfg: recall entries include verified Memoria observation IDs.

The snapshot stays private at /var/lib/live-infinita/memoria-local/navigation-recall.json and has a public copy at /godot/navigation-memory/recall.json containing only navigation summaries/evidence IDs. No API credential is sent to Godot or the browser. Native and web renderers poll every 30 seconds. Snapshots older than 180 seconds are rejected and recalled evidence is cleared. The API hierarchy/source kind and current world context are checked; the legacy cfg still has no original historical world identity.

At each new short movement segment, a capsule checks up to three metres ahead in 0.4m increments. The navigator compares direct, local remembered, Memoria remembered and eight other headings. Fully clear directions are preferred when available; otherwise it considers immediately safe shorter progress. Scoring includes distance to destination, visit history, actual local failures and retrieved blocked passages/successful steps. A recalled route always passes current physical checks. Obstacles beyond the final destination do not prevent arrival. When no sensed passage exists, the sensor rotates its probe headings and tries again on subsequent frames. It does not manufacture attempted-action failure evidence for a blocked speculative probe.

This is bounded local inference over experience and current geometry, not a globally optimal route planner or semantic generalization across unrelated obstacles. Local navigation experience remains a fallback if Memoria is unavailable. Both still respect the physical movement guard.

Causal diagnostics: a second ranking over the same perceived candidates excludes Memoria evidence. The memory_decisions counter and NOV_NAVIGATION_INFERENCE log with an observation ID are attributed to Memoria only when recalled evidence changes the selected next point. Detours already required by physical perception are not falsely credited to memory. These compare counterfactual choices for the current frame, not a live longitudinal memory-on/off experiment.

Validation:
- 20 Python tests cover ingestion and API-retrieved export, persistence, unchanged-data deduplication, malformed identities, world context, cache/window behavior and unavailable-source preservation.
- Eight Godot smokes pass: gait, traversal, grounded presentation, narration/audience, terrain alignment, experiential escape, camera stabilization and anticipation.
- Anticipation fixture: without memory selects (1,0); with retrieved successful-step fixture selects (0,1). A currently blocked recalled step is rejected. Expired evidence is cleared. The body starts deviating while a wall is still about three metres away, with zero attempted-action failures.
- Physical U enclosure reaches its goal with zero blocked attempts using perception (previously 33). The legacy trial-only U still demonstrates learned reuse.
- Installed Memoria.ia core in isolated SQLite/FastAPI accepted and durably reopened both summary kinds; the recall exporter fetched them through its authenticated recent-observations route and preserved their exact observation IDs. Production recall delivery is checked by the root installer.

Deployment:
sudo bash /home/etbra/live.infinita/deploy/apply-navigation-anticipation-008cg-root.sh

The combined installer updates the bridge/exporter, creates a narrowly writable public recall directory, validates recovered evidence, then exports and applies the renderer. Bridge and renderer installation have rollback backups; durable ingested records/checkpoints remain idempotent. The runtime world writer is unchanged. Success marker: 008CG_OK. Main log: /home/etbra/008cg-rollout.log. Renderer log: /home/etbra/008cg-renderer-rollout.log. Reload the live browser/source after deployment.

Operational proof still to collect: production log decisions with exact Memoria observation IDs and repeatable real routes showing fewer blocked attempts. Fixture success and ingestion alone must not be presented as that proof.
