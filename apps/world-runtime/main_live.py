from __future__ import annotations

import asyncio
from copy import deepcopy
from pathlib import Path
import json
import time
from typing import Any

from fastapi import Depends
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

import main as core
import main_spatial
from collective_intent import CollectiveIntentEngine
from collective_world import CollectiveWorldEvolver
from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from story_narrator import LiveStoryNarrator, StoryCue

app = main_spatial.app
APP_STARTED_AT = time.time()
TIKTOK_STATUS_FILE = core.DATA_DIR / "tiktok-status.json"
COLLECTIVE_STATE_FILE = core.DATA_DIR / "collective-intent-state.json"
collective_intent = CollectiveIntentEngine(COLLECTIVE_STATE_FILE)
story_narrator = LiveStoryNarrator()
_story_narration_lock = asyncio.Lock()
collective_evolver = (
    CollectiveWorldEvolver(main_spatial.cold_store)
    if main_spatial.cold_store is not None
    else None
)
collective_guarded = (
    GuardedMutationService(core.engine, decision_log_file=core.DATA_DIR / "mutation-decisions.jsonl")
    if collective_evolver is not None and isinstance(core.engine, ColdAuthoritativeWorldEngine)
    else None
)
_collective_task: asyncio.Task[None] | None = None


def _project_current_region_environment(
    projected: dict[str, Any],
    authoritative_message: dict[str, Any],
) -> dict[str, Any]:
    """Make the visual/audio environment follow the observer's current region."""
    local_world = projected.get("world")
    authoritative_world = authoritative_message.get("world")
    if not isinstance(local_world, dict) or not isinstance(authoritative_world, dict):
        return projected
    interest = local_world.get("interest") if isinstance(local_world.get("interest"), dict) else {}
    region_id = str(interest.get("current_region_id") or "").strip()
    if not region_id:
        return projected
    regions = authoritative_world.get("regions")
    if not isinstance(regions, list):
        return projected
    region = next(
        (row for row in regions if isinstance(row, dict) and str(row.get("id") or "") == region_id),
        None,
    )
    if region is None:
        return projected
    environment = dict(local_world.get("environment") or {})
    environment["biome"] = str(region.get("biome") or environment.get("biome") or "forest")
    environment["region_id"] = region_id
    metadata = region.get("metadata") if isinstance(region.get("metadata"), dict) else {}
    environment["region_label"] = str(metadata.get("label") or region_id)
    local_world["environment"] = environment
    return projected


def _sanitize_public_world_message(message: dict[str, Any]) -> dict[str, Any]:
    """Keep autonomous World State silent; only transient interaction cues are public narration."""
    result = deepcopy(message)
    world = result.get("world")
    if not isinstance(world, dict):
        return result
    narration = world.get("narration") if isinstance(world.get("narration"), dict) else {}
    cue = result.get("narration_cue") if isinstance(result.get("narration_cue"), dict) else None
    cue_text = str((cue or {}).get("text") or "").strip()
    if cue is not None and cue_text:
        world["narration"] = {
            **narration,
            "text": cue_text,
            "tts_enabled": False,
            "mode": str(cue.get("mode") or "interaction"),
            "cue_id": str(cue.get("cue_id") or ""),
        }
    else:
        world["narration"] = {
            **narration,
            "text": "",
            "tts_enabled": False,
            "mode": "silent",
        }
    return result


_original_wrap_world_message = main_spatial.spatial_session.wrap_world_message


def _public_wrap_world_message(message: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    projected = _original_wrap_world_message(message, view)
    projected = _project_current_region_environment(projected, message)
    return _sanitize_public_world_message(projected)


main_spatial.spatial_session.wrap_world_message = _public_wrap_world_message  # type: ignore[method-assign]


def _invalidate_spatial_topology() -> None:
    """Reload region graph after a collective chapter grows the map."""
    session = main_spatial.spatial_session
    refresh = getattr(main_spatial.cold_store, "refresh_manifest", None)
    if callable(refresh):
        refresh()
    cache = getattr(session, "cold_cache", None)
    if cache is not None:
        clear = getattr(cache, "clear", None)
        if callable(clear):
            clear()
    # Keep this exact SpatialSession instance: main_live has wrapped its public
    # projection method above to suppress autonomous narration and project local biomes.
    session._catalog = None  # type: ignore[attr-defined]
    session._region_grid = None  # type: ignore[attr-defined]
    session._cold_sequence = None  # type: ignore[attr-defined]


_original_audience_aggregator_ingest = core.aggregator.ingest


def _collective_audience_aggregator_ingest(
    event: dict[str, Any],
    now: float | None = None,
) -> list[dict[str, Any]]:
    proposals = _original_audience_aggregator_ingest(event, now=now)
    collective_intent.ingest_telemetry(event, now=now)
    return proposals


core.aggregator.ingest = _collective_audience_aggregator_ingest  # type: ignore[method-assign]


def _response_story_summary(response: Any) -> dict[str, Any]:
    result: dict[str, Any] = {"status_code": int(getattr(response, "status_code", 0) or 0)}
    body = getattr(response, "body", b"")
    if not body:
        return result
    try:
        payload = json.loads(body.decode("utf-8"))
    except (AttributeError, UnicodeDecodeError, json.JSONDecodeError):
        return result
    if not isinstance(payload, dict):
        return result
    result["ok"] = bool(payload.get("ok"))
    result["world_mutated"] = bool(payload.get("world_mutated", payload.get("event")))
    event = payload.get("event")
    if isinstance(event, dict):
        result["event"] = {
            "event_id": event.get("event_id"),
            "action": event.get("action"),
            "type": event.get("type"),
        }
    validation = payload.get("validation")
    if isinstance(validation, dict):
        result["validation"] = {
            "accepted": validation.get("accepted"),
            "action": validation.get("action"),
        }
    result["ai_fallback"] = payload.get("ai_fallback")
    return result


async def _broadcast_story_cue(cue: StoryCue) -> None:
    """Send voice cue to audio and a matching transient caption to visual clients."""
    payload = cue.as_dict()
    await core.broadcast({"type": "narration_cue", "cue": payload})
    # A second world projection updates the existing Godot narration panel without
    # persisting presentation prose into authoritative World State.
    await main_spatial.spatial_broadcast({
        "type": "world_state",
        "world": core.engine.load_world(),
        "narration_cue": payload,
    })


async def _narrate_comment(comment: dict[str, Any], interaction_result: dict[str, Any]) -> None:
    try:
        async with _story_narration_lock:
            cue = await asyncio.to_thread(
                story_narrator.render_interaction,
                config=core.integrations.load(),
                comment=comment,
                world=core.engine.load_world(),
                collective_state=collective_intent.snapshot(),
                interaction_result=interaction_result,
            )
            await _broadcast_story_cue(cue)
    except asyncio.CancelledError:
        raise
    except Exception:
        # Narration is presentation only; it can never fail the audience/runtime path.
        return


_original_gateway_payload = core.process_gateway_payload


async def _collective_gateway_payload(payload: dict[str, Any]):
    """Observe audience language for collective direction and story narration."""
    source = str(payload.get("source") or "").strip().lower()
    kind = str(payload.get("kind") or "text").strip().lower()
    signal: dict[str, Any] | None = None
    story_comment: dict[str, Any] | None = None
    if source in {"tiktok", "youtube"} and kind == "text":
        story_comment = story_narrator.observe_comment(
            source=source,
            actor_id=str(payload.get("actor_id") or "anonymous"),
            display_name=payload.get("display_name"),
            text=str(payload.get("text") or ""),
            source_event_id=str(payload.get("source_event_id") or "") or None,
        )
        signal = collective_intent.ingest_comment(
            source=source,
            actor_id=str(payload.get("actor_id") or "anonymous"),
            display_name=payload.get("display_name"),
            text=str(payload.get("text") or ""),
        )
    response = await _original_gateway_payload(payload)
    if signal is not None:
        await core.broadcast({
            "type": "collective_intent",
            "signal": signal,
            "state": collective_intent.snapshot(),
        })
    if story_comment is not None:
        # Do not hold the source bridge HTTP request while the narrator phrases the story.
        asyncio.create_task(
            _narrate_comment(story_comment, _response_story_summary(response)),
            name=f"live-story-{story_comment.get('source_event_id') or int(time.time() * 1000)}",
        )
    return response


core.process_gateway_payload = _collective_gateway_payload


def _commit_collective_evolution(decision: dict[str, Any]) -> dict[str, Any]:
    if collective_evolver is None or collective_guarded is None:
        raise RuntimeError("collective evolution requires cold authoritative world")
    world = core.engine.load_world()
    planned = collective_evolver.plan(world, decision)
    result = collective_guarded.commit(
        list(planned["operations"]),
        principal={
            "source": "collective_intent",
            "actor_id": "collective-audience",
            "authority": "system",
            "subject_entity_id": None,
        },
        context={
            "collective_intent": {
                "theme": planned["theme"],
                "chapter": planned["chapter"],
                "score": decision.get("dominant_score"),
                "dominance": decision.get("dominance"),
                "contributors": decision.get("contributors"),
            },
            "target_region_id": planned.get("region_id"),
            "target_entity_id": planned.get("target_entity_id"),
        },
        narration=str(planned["narration"]),
    )
    return {"planned": planned, "result": result}


async def _collective_evolution_loop() -> None:
    while True:
        try:
            decision = collective_intent.next_evolution()
            if decision is not None and collective_evolver is not None and collective_guarded is not None:
                committed = await asyncio.to_thread(_commit_collective_evolution, decision)
                planned = committed["planned"]
                result = committed["result"]
                if result.get("ok"):
                    event = result.get("event") or {}
                    event_id = str(event.get("event_id") or "")
                    await asyncio.to_thread(
                        collective_intent.mark_applied,
                        decision,
                        event_id=event_id,
                        region_id=planned.get("region_id"),
                    )
                    _invalidate_spatial_topology()
                    evolution = {
                        "theme": planned["theme"],
                        "chapter": planned["chapter"],
                        "region_id": planned.get("region_id"),
                        "target_entity_id": planned.get("target_entity_id"),
                        "contributors": decision.get("contributors"),
                    }
                    await main_spatial.spatial_broadcast({
                        "type": "world_state",
                        "world": result["world"],
                        "event": result["event"],
                        "delta": result["delta"],
                        "collective_evolution": evolution,
                    })
                    state = collective_intent.snapshot()
                    await core.broadcast({
                        "type": "collective_intent",
                        "state": state,
                        "evolution": evolution,
                    })
                    async with _story_narration_lock:
                        cue = await asyncio.to_thread(
                            story_narrator.render_collective_evolution,
                            config=core.integrations.load(),
                            world=result["world"],
                            collective_state=state,
                            evolution=evolution,
                        )
                        await _broadcast_story_cue(cue)
                else:
                    reason = str((result.get("decision") or {}).get("reason") or "mutation rejected")
                    await asyncio.to_thread(collective_intent.mark_failed, decision, reason)
                    await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            decision = locals().get("decision")
            if isinstance(decision, dict):
                try:
                    await asyncio.to_thread(collective_intent.mark_failed, decision, type(exc).__name__)
                except Exception:
                    pass
            await asyncio.sleep(10.0)
        await asyncio.sleep(2.0)


async def _start_collective_evolution() -> None:
    global _collective_task
    if _collective_task is None or _collective_task.done():
        _collective_task = asyncio.create_task(
            _collective_evolution_loop(),
            name="live-infinita-collective-evolution",
        )


async def _stop_collective_evolution() -> None:
    global _collective_task
    task = _collective_task
    _collective_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


app.add_event_handler("startup", _start_collective_evolution)
app.add_event_handler("shutdown", _stop_collective_evolution)


def _read_tiktok_status() -> dict[str, Any]:
    if not TIKTOK_STATUS_FILE.exists():
        return {"state": "not_started", "updated_at_unix": None}
    try:
        value = json.loads(TIKTOK_STATUS_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"state": "unknown", "updated_at_unix": None}
    except (OSError, ValueError):
        return {"state": "unknown", "updated_at_unix": None}


def _monitor_activity(limit: int = 30) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in core.read_jsonl(core.AUDIENCE_EVENTS_FILE)[-limit:]:
        actor = item.get("actor") or {}
        rows.append({
            "channel": "audience",
            "kind": item.get("kind", "event"),
            "source": item.get("source", "unknown"),
            "actor": actor.get("display_name") or actor.get("actor_id") or "Participante",
            "at_unix": item.get("received_at_unix"),
        })
    try:
        world_events = core.engine.read_jsonl(core.engine.events_file)[-limit:]
    except Exception:
        world_events = []
    for item in world_events:
        context = item.get("context") or {}
        rows.append({
            "channel": "world",
            "kind": item.get("action") or item.get("type") or "world_event",
            "source": item.get("source", "unknown"),
            "actor": context.get("display_name") or context.get("actor_id") or "Sistema",
            "at_unix": item.get("committed_at_unix") or context.get("observed_at_unix"),
        })
    rows.sort(key=lambda item: float(item.get("at_unix") or 0), reverse=True)
    return rows[:limit]


@app.get("/api/audience/collective-intent")
async def current_collective_intent() -> JSONResponse:
    return JSONResponse({
        "state": collective_intent.snapshot(),
        "evolutions": collective_intent.evolutions[-20:],
        "last_failure": collective_intent.last_failure,
        "story_audience": story_narrator.active_snapshot(),
    })


@app.get("/api/manage/monitor", dependencies=[Depends(core.require_operator)])
async def current_manager_monitor() -> JSONResponse:
    now = time.time()
    world = core.engine.load_world()
    audience_events = core.read_jsonl(core.AUDIENCE_EVENTS_FILE)
    counts = {kind: sum(1 for row in audience_events if row.get("kind") == kind) for kind in ("join", "like", "gift")}
    integrations = core.integrations.public_status()
    tiktok = _read_tiktok_status()
    updated = tiktok.get("updated_at_unix")
    if isinstance(updated, (int, float)):
        tiktok["age_seconds"] = max(0, round(now - updated))
        tiktok["stale"] = now - updated > 90
    else:
        tiktok["age_seconds"] = None
        tiktok["stale"] = True
    if main_spatial.cold_store is not None:
        refresh = getattr(main_spatial.cold_store, "refresh_manifest", None)
        if callable(refresh):
            refresh()
        entities_total = main_spatial.cold_store.entities_total()
    else:
        entities_total = len(world.get("entities", []))
    replay = core.engine.verify_replay()
    return JSONResponse({
        "generated_at_unix": now,
        "runtime": {"state": "online", "uptime_seconds": round(now - APP_STARTED_AT)},
        "tiktok": {**tiktok, "configured": integrations["tiktok"]["configured"], "unique_id": integrations["tiktok"]["unique_id"]},
        "openai": {"configured": integrations["openai"]["configured"], "model": integrations["openai"]["model"]},
        "world": {
            "version": world.get("version"),
            "sequence": world.get("sequence"),
            "entities": entities_total,
            "regions": len(world.get("regions", [])) if isinstance(world.get("regions"), list) else 0,
            "period": (world.get("environment") or {}).get("period"),
            "story": world.get("story") if isinstance(world.get("story"), dict) else {},
            "replay_ok": bool(replay.get("ok")),
        },
        "collective": collective_intent.snapshot(now),
        "narrator": {
            "policy": "interaction_only",
            "audience": story_narrator.active_snapshot(now),
        },
        "websocket": {"clients": len(main_spatial.session_views)},
        "audience": {"total": len(audience_events), **counts},
        "actors": {"total": len(core.actors.actors()), "bound": len(core.bindings.current())},
        "activity": _monitor_activity(),
    })


def _is_legacy_static_mount(route: object) -> bool:
    return isinstance(route, Mount) and route.path in {"", "/", "/manage"}


app.router.routes = [route for route in app.router.routes if not _is_legacy_static_mount(route)]


@app.get("/manage", include_in_schema=False)
@app.get("/manage/", include_in_schema=False)
async def legacy_manager_redirect() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=308)


@app.middleware("http")
async def manager_shell_security_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path in {"/app.js", "/style.css", "/monitoring.css", "/visibility.css"}:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'"
        )
    return response


app.mount("/gdscript", StaticFiles(directory=str(Path(core.RENDERER_DIR)), html=True), name="gdscript-renderer")
app.mount("/", StaticFiles(directory=str(Path(core.MANAGER_DIR)), html=True), name="manager")
