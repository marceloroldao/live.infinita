# Situation/action/outcome patterns — 008EG

## Implemented behavior

Experimental nov_navigation_patterns.gd groups physically measured outcomes by a relative local sensing signature instead of goal|position addresses. Its context encodes observed and clear-ahead sectors relative to goal direction; it contains no world coordinates, gap locations or full route. Separate measurement evidence may retain start/goal coordinates for audit.

At initial contour contact an optional pattern adapter can recommend a tangent side. Contour only accepts that side if a perception candidate is physically viable. Its normal corridor release, expanding excursions, goal resets and physics checks remain unchanged. Explicit experiment exploration alternates both initial sides before selecting from evidence; this deliberate training control is distinct from a learned recommendation.

The adapter is disabled by default and production contour has no attached pattern memory. No native journey collector, promotion bridge or live panel is wired to this module yet. The current root 008EF installer may copy the optional contour hook, but cannot enable patterns or install a working pattern pipeline. There is no 008EG production installer.

## Evidence and penalties

Each accepted record contains relative context, attempted side, physical outcome, actual distance and initial remaining distance. Cost is normalized actual distance / initial remaining distance. Executed blocked or stuck-recovery outcomes add a heuristic error penalty of 20 to their context/action average. This coefficient and the 20% preference margin are application policy, not values autonomously inferred by the core.

At least two samples per side are required; only the latest 32 samples per context/action participate. The complete bounded buffer has at most 512 records. Contradictions coexist; no permanent forbidden side is created. Weak/equal evidence, unknown signatures, absent successful alternatives and disabled mode abstain. Shutdown/goal-change interruptions, predictions, sensed-only rejections, duplicate attempt IDs within the retained buffer, and nonfinite/invalid costs are rejected.

Success after a long detour remains a success with a larger cost. The physical comparison tests costly successful routes, not actual collision/error learning. Separate component tests check fabricated blocked samples solely to verify penalty mechanics; those synthetic samples are never sent to the core or production.

## Real physical experiment

Godot actual capsules and static wall bodies, fixed speed 4 m/s and dt 0.1, no BFS/global route search. Four training journeys at start (-86,-80), goal (-68,-80), wall x=-80 and opening z=-130 explore both sides twice. Measured costs determine the preferred side; the learner receives no opening label or hard-authored correct side.

Held-out case changes start to (-86,-60), goal to (-64,-60), and translates the opening to z=-110. Goal|position addresses differ; the local relative sensing signature matches.

| Held-out arm | Actual distance | Simulated time |
| --- | ---: | ---: |
| Perception, same exploration policy | 234.572 m | 70.4 s |
| Pattern samples retained in RAM | 106.606 m | 32.0 s |
| Pattern samples recovered from reopened real core | 106.606 m | 32.0 s |

The recovered pattern changes the initial side relative to the memory-free contact decision. Every measured arm arrives with zero collisions, zero stuck rescues and zero global route builds. Legacy causal-step counters are not wired to this adapter; separate pattern initial-side evidence and full physical outcomes establish this isolated comparison.

The runner stores four physical outcome events through pinned Memoria.ia SDK dfd87c995b50c49b45a9d5dd4c43cce456983d4f, SQLite with fallback disabled. It reopens the isolated store, validates hash-derived IDs and exact event/provenance equality, and builds recommendations only from recovered rows. Both preferred-side contributing observation IDs appear in decision evidence. Actual core count is four.

Core associations are deferred and retrieval uses recent observations. Application code encodes signatures, groups matching samples and computes preferences. This demonstrates contribution from persisted/recovered experience in this adapter, not that the core autonomously discovers navigation concepts or computes these policies. Production promotion eligibility is explicitly bypassed only in this isolated experiment.

## Changed environment and limitations

Move the held-out opening to z=-10: its initial local signature remains identical. Perception now travels 106.606 m / 32.0 s, while the stale preferred side travels 234.572 m / 70.4 s. This regression is deliberately retained in evidence.

Twelve subsequent real training attempts (six per side) on the changed geometry cause the recommendation to favor the opposite side; a new attempt returns to 106.606 m / 32.0 s. Old samples remain. This revision is demonstrated in RAM, not yet stored/recovered after the change through the core. Deliberate balanced training is not autonomous live curiosity.

Local observations can alias different unseen worlds. This first pattern is an exact relative signature match, not broad semantic generalization. The experiment covers translation, changed goal and mirrored distant opening; it does not establish benefit in arbitrary worlds or long-running live sessions. World/material/capsule scope separation, automatic actual journey feedback, promotion and recovery reconciliation are required before live enablement.

## Reproduction and validation

Sync renderer scripts into isolated /home/etbra/008bz-godot-test, then run:

    /opt/live.infinita/.venv/bin/python tools/run_navigation_patterns_008eg.py --output-dir /home/etbra/008eg-pattern-results

The runner uses temporary, exclusive SQLite state and changes no live services, production keys or memory history. Physical scripts and component tests are committed; regression results accompany this document. Frozen v0.1.0 remains unchanged.
