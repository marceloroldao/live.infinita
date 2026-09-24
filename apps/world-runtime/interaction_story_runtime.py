from __future__ import annotations

import asyncio
from typing import Any

import main as core
import main_live
import main_spatial
from cold_engine import ColdAuthoritativeWorldEngine
from interaction_story import InteractionStoryContinuity
from mutation_gate_service import GuardedMutationService
from story_narrator_v1 import StoryContinuityNarrator


# Replace only the presentation narrator. The interaction parser, mutation gate and
# World State authority remain exactly where they already live.
main_live.story_narrator = StoryContinuityNarrator()
story_continuity = InteractionStoryContinuity(max_beats=16)
_story_guarded = (
    GuardedMutationService(core.engine, decision_log_file=core.DATA_DIR / "mutation-decisions.jsonl")
    if isinstance(core.engine, ColdAuthoritativeWorldEngine)
    else None
)
_base_gateway = main_live._original_gateway_payload


def _eligible_comment(payload: dict[str, Any]) -> bool:
    return (
        str(payload.get("source") or "").strip().lower() in {"tiktok", "youtube", "simulator"}
        and str(payload.get("kind") or "text").strip().lower() == "text"
    )


def _commit_story_consequence(
    payload: dict[str, Any],
    interaction_result: dict[str, Any],
) -> dict[str, Any] | None:
    if _story_guarded is None or not _eligible_comment(payload):
        return None
    world = core.engine.load_world()
    planned = story_continuity.plan(
        world=world,
        comment=payload,
        interaction_result=interaction_result,
        collective_state=main_live.collective_intent.snapshot(),
        now=core.time.time(),
    )
    if planned is None:
        return None

    event = interaction_result.get("event") if isinstance(interaction_result.get("event"), dict) else {}
    result = _story_guarded.commit(
        [planned["operation"]],
        principal={
            "source": "interaction_story",
            "actor_id": "story-continuity",
            "authority": "system",
            "subject_entity_id": None,
        },
        context={
            "source_event_id": payload.get("source_event_id"),
            "source": payload.get("source"),
            "actor_id": payload.get("actor_id"),
            "interaction_world_event_id": event.get("event_id"),
            "interaction_action": planned["beat"].get("action"),
            "story_beat": planned["beat"].get("beat"),
        },
        narration="",
    )
    if not result.get("ok"):
        return None
    return {"planned": planned, "result": result}


async def record_story_consequence(
    payload: dict[str, Any],
    response: Any,
) -> dict[str, Any] | None:
    summary = main_live._response_story_summary(response)
    if not bool(summary.get("world_mutated")):
        return None
    committed = await asyncio.to_thread(_commit_story_consequence, payload, summary)
    if committed is None:
        return None
    result = committed["result"]
    planned = committed["planned"]
    await main_spatial.spatial_broadcast({
        "type": "world_state",
        "world": result["world"],
        "event": result["event"],
        "delta": result["delta"],
        "story_beat": planned["beat"],
    })
    await core.broadcast({
        "type": "story_beat",
        "beat": planned["beat"],
        "story": planned["story"],
    })
    return committed


async def _story_aware_gateway(payload: dict[str, Any]):
    response = await _base_gateway(payload)
    try:
        await record_story_consequence(payload, response)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        # Story continuity is a secondary deterministic projection. A failure here
        # must never turn a successfully accepted audience action into an HTTP error.
        print(f"[story] continuity update skipped: {type(exc).__name__}: {exc}", flush=True)
    return response


# main_live calls this variable after it has observed the audience comment but
# before it schedules narration. Interposing here guarantees the narrator sees
# the confirmed, persisted consequence rather than anticipating it.
main_live._original_gateway_payload = _story_aware_gateway