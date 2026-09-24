from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any

from fastapi import Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import main as core
import main_context_live
import main_live
import main_spatial
from cognitive_shadow import summarize_shadow_file
from memoria_v2_adapter import build_nov_cognitive_frame, to_memoria_v2_request_payload
from route_precedence import promote_api_route_before_root
from story_narrator import NarrationSuppressed


app = main_context_live.app


def _flag_enabled(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


COGNITIVE_GYM_ENABLED = _flag_enabled("LIVE_INFINITA_MEMORIA_V2_COGNITIVE_GYM")


class ManagerSimulatorCommentRequest(BaseModel):
    display_name: str = Field(default="Visitante de teste", min_length=1, max_length=80)
    actor_id: str = Field(
        default="manager-viewer-1",
        min_length=1,
        max_length=100,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    text: str = Field(min_length=1, max_length=500)
    allow_during_live: bool = False


def _entity_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }


def _shadow_file():
    return main_spatial._world_data_root() / "memoria-v2-shadow.jsonl"


def _fresh_tiktok_live(now: float | None = None) -> tuple[bool, dict[str, Any]]:
    status = main_live._read_tiktok_status()
    at = float(now if now is not None else time.time())
    updated = status.get("updated_at_unix")
    fresh = isinstance(updated, (int, float)) and at - float(updated) <= 90.0
    return bool(status.get("state") == "connected" and fresh), status


def _simulator_world_summary() -> dict[str, Any]:
    world = core.engine.load_world()
    environment = world.get("environment") if isinstance(world.get("environment"), dict) else {}
    story = world.get("story") if isinstance(world.get("story"), dict) else {}
    return {
        "version": world.get("version"),
        "sequence": world.get("sequence"),
        "period": environment.get("period"),
        "weather": environment.get("weather"),
        "biome": environment.get("biome"),
        "chapter": story.get("chapter"),
    }


async def _manager_simulator_runtime(payload: dict[str, Any]) -> JSONResponse:
    """Apply the same safe audience policy to a Manager-only simulated viewer."""
    try:
        normalized, proposed, validation = core.pipeline.process(payload)
    except ValueError as exc:
        raise core.HTTPException(status_code=400, detail=str(exc)) from exc

    if validation.accepted and validation.action in main_spatial._AUDIENCE_AUTO_ACTIONS:
        cloned = dict(payload)
        metadata = dict(cloned.get("metadata") or {})
        metadata["audience_auto_approved"] = True
        cloned["metadata"] = metadata
        return await main_live._original_gateway_payload(cloned)

    if not validation.accepted and normalized.kind == "text":
        return await main_spatial._audience_ai_fallback(
            normalized,
            main_live._original_gateway_payload,
        )

    if validation.accepted:
        await main_spatial._observe_unhandled_audience(normalized)
        return JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "requires_operator": True,
            "proposed_action": proposed.action,
        }, status_code=202)

    return JSONResponse({
        "ok": True,
        "world_mutated": False,
        "audience_comment": "observed",
    }, status_code=202)


async def _build_cognitive_projection(observer_id: str):
    normalized_observer = observer_id.strip()
    if normalized_observer != "nov":
        raise core.HTTPException(
            status_code=422,
            detail="cognitive gym de produção atualmente suporta observer_id=nov",
        )

    async with core.world_lock:
        world = core.engine.load_world()
        entities, entities_total, scope = main_context_live._context_entities(
            world,
            bound_entity_id=normalized_observer,
        )
        by_id = _entity_map(entities)
        observer = by_id.get(normalized_observer)
        if observer is None and main_spatial.cold_store is not None:
            candidate = main_spatial.cold_store.get_entity(normalized_observer)
            if isinstance(candidate, dict):
                observer = candidate
                by_id[normalized_observer] = candidate
        if observer is None:
            raise core.HTTPException(status_code=404, detail="observador Nov não encontrado")

        package = main_context_live.context_compiler.compile(
            world=world,
            actor=None,
            bound_entity_id=normalized_observer,
            entities=entities,
            entities_total=entities_total,
            scope={**scope, "purpose": "memoria-v2-cognitive-gym"},
        )
        frame = build_nov_cognitive_frame(
            world=world,
            observer=observer,
            targets=by_id,
            context_digest=package.digest,
        )
        return frame, package


@app.get("/api/cognitive/v2/frame", dependencies=[Depends(core.require_operator)])
async def cognitive_v2_frame(observer_id: str = "nov") -> JSONResponse:
    if not COGNITIVE_GYM_ENABLED:
        raise core.HTTPException(
            status_code=503,
            detail="Memoria V2 Cognitive Gym desabilitado por feature flag",
        )

    frame, package = await _build_cognitive_projection(observer_id)
    requests = [
        to_memoria_v2_request_payload(frame, proposal_id=item.proposal_id)
        for item in frame.available_interventions
    ]
    return JSONResponse({
        "ok": True,
        "world_mutated": False,
        "mode": "read-only-cognitive-projection",
        "context_digest": package.digest,
        "frame": frame.to_dict(),
        "memoria_v2_requests": requests,
    })


@app.get("/api/cognitive/v2/shadow/metrics", dependencies=[Depends(core.require_operator)])
async def cognitive_v2_shadow_metrics() -> JSONResponse:
    summary = summarize_shadow_file(_shadow_file())
    return JSONResponse({
        "ok": True,
        "world_mutated": False,
        "mode": "passive-shadow-observer",
        "direct_world_write": False,
        "selection_authority": False,
        "metrics": summary,
    })


@app.get("/api/manage/simulator/state", dependencies=[Depends(core.require_operator)])
async def manager_simulator_state() -> JSONResponse:
    live_active, tiktok = _fresh_tiktok_live()
    audience = main_live.story_narrator.active_snapshot()
    participant_keys = [
        key for key in audience.get("participant_keys", [])
        if str(key).startswith("simulator:")
    ]
    return JSONResponse({
        "ok": True,
        "mode": "manager-live-simulator",
        "live_active": live_active,
        "tiktok_state": tiktok.get("state"),
        "simulated_participants": len(participant_keys),
        "collective": main_live.collective_intent.snapshot(),
        "world": _simulator_world_summary(),
    })


@app.post("/api/manage/simulator/comment", dependencies=[Depends(core.require_operator)])
async def manager_simulator_comment(request: ManagerSimulatorCommentRequest) -> JSONResponse:
    live_active, tiktok = _fresh_tiktok_live()
    if live_active and not request.allow_during_live:
        raise core.HTTPException(
            status_code=409,
            detail="TikTok LIVE está conectada; simulador bloqueado para não misturar audiência real com teste",
        )

    event_id = f"manager-sim-{request.actor_id}-{time.time_ns()}"
    payload = {
        "source": "simulator",
        "source_event_id": event_id,
        "actor_id": request.actor_id,
        "display_name": request.display_name,
        "kind": "text",
        "text": request.text,
        "metadata": {
            "manager_simulator": True,
            "simulated": True,
            "tiktok_state_at_send": tiktok.get("state"),
        },
    }

    story_comment = main_live.story_narrator.observe_comment(
        source="simulator",
        actor_id=request.actor_id,
        display_name=request.display_name,
        text=request.text,
        source_event_id=event_id,
    )
    signal = main_live.collective_intent.ingest_comment(
        source="simulator",
        actor_id=request.actor_id,
        display_name=request.display_name,
        text=request.text,
    )

    runtime_response = await _manager_simulator_runtime(payload)
    collective_state = main_live.collective_intent.snapshot()
    await core.broadcast({
        "type": "collective_intent",
        "signal": signal,
        "state": collective_state,
        "simulated": True,
    })

    cue = None
    narration_suppressed: str | None = None
    try:
        async with main_live._story_narration_lock:
            cue = await asyncio.to_thread(
                main_live.story_narrator.render_interaction,
                config=core.integrations.load(),
                comment=story_comment,
                world=core.engine.load_world(),
                collective_state=collective_state,
                interaction_result=main_live._response_story_summary(runtime_response),
            )
            await main_live._broadcast_story_cue(cue)
    except NarrationSuppressed as exc:
        narration_suppressed = str(exc) or "collective_cooldown"
    except Exception:
        narration_suppressed = "narrator_unavailable"

    return JSONResponse({
        "ok": True,
        "mode": "manager-live-simulator",
        "simulated": True,
        "source_event_id": event_id,
        "runtime": main_live._response_story_summary(runtime_response),
        "narration_cue": cue.as_dict() if cue is not None else None,
        "narration_suppressed": narration_suppressed,
        "collective": collective_state,
        "world": _simulator_world_summary(),
    })


_original_context_health = main_context_live.context_health


async def cognitive_health() -> JSONResponse:
    response = await _original_context_health()
    payload = json.loads(response.body.decode("utf-8")) if response.body else {}
    shadow_summary = summarize_shadow_file(_shadow_file())
    payload["cognitive_gym_v2"] = {
        "enabled": COGNITIVE_GYM_ENABLED,
        "mode": "read-only-cognitive-projection",
        "direct_world_write": False,
        "observer": "nov",
        "contract": "CognitiveFrame -> Memoria V2 request payload",
        "shadow_observer": {
            "records": shadow_summary.get("records", 0),
            "exact_match_rate": shadow_summary.get("exact_match_rate"),
            "direct_world_write": False,
            "selection_authority": False,
        },
    }
    if COGNITIVE_GYM_ENABLED:
        pipeline = list(payload.get("pipeline") or [])
        if "cognitive-gym-v2" not in pipeline:
            try:
                index = pipeline.index("runtime")
            except ValueError:
                index = len(pipeline)
            pipeline.insert(index, "cognitive-gym-v2")
        payload["pipeline"] = pipeline
    return JSONResponse(payload, status_code=response.status_code)


main_context_live._replace_route("/api/health", "GET", cognitive_health)


# main_context_live is imported after main_live has mounted Manager at '/'. Its
# preview, cognitive and Manager extension routes therefore need explicit precedence.
promote_api_route_before_root(app, "/api/ai/context/preview")
promote_api_route_before_root(app, "/api/cognitive/v2/frame")
promote_api_route_before_root(app, "/api/cognitive/v2/shadow/metrics")
promote_api_route_before_root(app, "/api/manage/simulator/state")
promote_api_route_before_root(app, "/api/manage/simulator/comment")
