from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from typing import Any

from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

import main as core
import main_live
import main_spatial
from apps.context.compiler import CONTEXT_SCHEMA_VERSION, ContextCompiler, ContextPackage


app = main_live.app
context_compiler = ContextCompiler(max_entities=64, max_regions=32)
_REFERENCE_ENTITY_IDS = ("nov", "fire_01", "shelter_marker", "ancient_tree")


class StaleContextError(RuntimeError):
    def __init__(self, *, expected: dict[str, Any], current: dict[str, Any]) -> None:
        super().__init__("AI proposal context is stale")
        self.expected = expected
        self.current = current


def _world_ref(world: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": int(world.get("version", 0)),
        "sequence": int(world.get("sequence", 0)),
        "state_hash": world.get("state_hash"),
    }


def _context_entities(
    world: dict[str, Any],
    *,
    bound_entity_id: str | None,
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    store = main_spatial.cold_store
    if store is None:
        rows = [row for row in world.get("entities", []) if isinstance(row, dict)]
        return rows, len(rows), {"mode": "resident-world"}

    refresh = getattr(store, "refresh_manifest", None)
    if callable(refresh):
        refresh()

    cold = world.get("cold_entities") if isinstance(world.get("cold_entities"), dict) else {}
    anchor_id = str(
        bound_entity_id
        or cold.get("default_observer_entity_id")
        or "nov"
    ).strip()
    anchor_region = store.entity_region(anchor_id) if anchor_id else None

    rows: list[dict[str, Any]] = []
    region_ids: list[str] = []
    if anchor_region:
        region_ids.append(anchor_region)
        rows.extend(store.load_region(anchor_region))

    seen = {str(row.get("id") or "") for row in rows if isinstance(row, dict)}
    for entity_id in _REFERENCE_ENTITY_IDS:
        if entity_id in seen:
            continue
        entity = store.get_entity(entity_id)
        if isinstance(entity, dict):
            rows.append(entity)
            seen.add(entity_id)

    scope = {
        "mode": "cold-region-plus-anchors",
        "anchor_entity_id": anchor_id or None,
        "region_ids": region_ids,
        "reference_entity_ids": [entity_id for entity_id in _REFERENCE_ENTITY_IDS if entity_id in seen],
    }
    return rows, store.entities_total(), scope


async def compile_ai_context(*, source: str, actor_id: str) -> ContextPackage:
    normalized_source = source.strip().lower()
    normalized_actor_id = actor_id.strip()
    actor_key = f"{normalized_source}:{normalized_actor_id}"
    async with core.world_lock, core.actor_lock:
        world = core.engine.load_world()
        actor = core.actors.get(normalized_source, normalized_actor_id)
        bound_entity_id = core.bindings.current().get(actor_key)
        entities, entities_total, scope = _context_entities(
            world,
            bound_entity_id=bound_entity_id,
        )
        return context_compiler.compile(
            world=world,
            actor=actor,
            bound_entity_id=bound_entity_id,
            entities=entities,
            entities_total=entities_total,
            scope=scope,
        )


def _context_store_fields(package: ContextPackage) -> dict[str, Any]:
    actor_view = package.payload.get("actor") or {}
    binding_view = package.payload.get("binding") or {}
    return {
        "context_digest": package.digest,
        "context_schema_version": package.payload.get("schema_version"),
        "context_world_version": package.world_version,
        "context_world_sequence": package.world_sequence,
        "context_world_state_hash": package.world_state_hash,
        "context_actor_key": actor_view.get("actor_key"),
        "context_bound_entity_id": binding_view.get("entity_id"),
        "context_scope": package.payload.get("scope") or {},
    }


def _expected_world_from_proposal(proposal: dict[str, Any]) -> dict[str, Any]:
    context_ref = dict(proposal.get("context") or {})
    if not context_ref.get("digest"):
        raise core.HTTPException(
            status_code=409,
            detail="proposta AI legada sem Context Package; gere uma nova proposta",
        )
    return {
        "version": int(context_ref.get("world_version", -1)),
        "sequence": int(context_ref.get("world_sequence", -1)),
        "state_hash": context_ref.get("world_state_hash"),
    }


_original_commit_action = core.engine.commit_action


def _context_guarded_commit_action(
    action: str,
    source: str = "runtime",
    context: dict[str, Any] | None = None,
):
    safe_context = deepcopy(context or {})
    metadata = dict(safe_context.get("metadata") or {})
    expected = metadata.pop("_context_expected_world", None)
    safe_context["metadata"] = metadata
    if isinstance(expected, dict):
        current = _world_ref(core.engine.load_world())
        normalized_expected = {
            "version": int(expected.get("version", -1)),
            "sequence": int(expected.get("sequence", -1)),
            "state_hash": expected.get("state_hash"),
        }
        if current != normalized_expected:
            raise StaleContextError(expected=normalized_expected, current=current)
    return _original_commit_action(action, source=source, context=safe_context)


core.engine.commit_action = _context_guarded_commit_action  # type: ignore[method-assign]


_original_observe_actor = core.observe_actor


async def _evidence_safe_observe_actor(*, source: str, **kwargs: Any) -> bool:
    if str(source).strip().lower() == "agent":
        return False
    return await _original_observe_actor(source=source, **kwargs)


core.observe_actor = _evidence_safe_observe_actor


@app.post("/api/ai/context/preview", dependencies=[Depends(core.require_operator)])
async def preview_ai_context(request: core.AIInterpretRequest) -> JSONResponse:
    package = await compile_ai_context(source=request.source, actor_id=request.actor_id)
    return JSONResponse({
        "ok": True,
        "world_mutated": False,
        "context": package.to_dict(),
    })


async def create_ai_proposal(request: core.AIInterpretRequest) -> JSONResponse:
    router = core.build_ai_router()
    package = await compile_ai_context(source=request.source, actor_id=request.actor_id)
    try:
        proposal = await asyncio.to_thread(
            router.propose,
            request.text,
            context=package.to_dict(),
        )
    except core.AIRouterError as exc:
        raise core.HTTPException(status_code=502, detail=str(exc)) from exc

    proposal_dict = proposal.to_dict()
    actionable = bool(proposal.actionable and proposal.confidence >= core.AI_MIN_CONFIDENCE)
    async with core.ai_lock:
        stored = core.ai_proposals.create(
            action=proposal.action,
            confidence=proposal.confidence,
            reason=proposal.reason,
            original_text=proposal.original_text,
            model=proposal.model,
            gateway_text=proposal_dict.get("gateway_text") if actionable else None,
            actionable=actionable,
            source=request.source.strip().lower(),
            actor_id=request.actor_id.strip(),
            display_name=request.display_name,
            metadata=request.metadata,
            **_context_store_fields(package),
        )
    await core.broadcast({"type": "ai_proposal", "proposal": stored})
    return JSONResponse({"ok": True, "world_mutated": False, "proposal": stored}, status_code=202)


async def _mark_stale(proposal_id: str, exc: StaleContextError) -> dict[str, Any]:
    async with core.ai_lock:
        stale = core.ai_proposals.mark_stale(
            proposal_id,
            current_world_version=int(exc.current.get("version", 0)),
            current_world_sequence=int(exc.current.get("sequence", 0)),
            current_world_state_hash=exc.current.get("state_hash"),
        )
    await core.broadcast({"type": "ai_proposal", "proposal": stale})
    return stale


async def commit_ai_proposal(proposal_id: str) -> JSONResponse:
    async with core.ai_lock:
        proposal = core.ai_proposals.get(proposal_id)
    if proposal is None:
        raise core.HTTPException(status_code=404, detail="proposta AI não encontrada")
    if proposal.get("status") != "pending":
        raise core.HTTPException(status_code=409, detail="proposta AI não está pendente")
    gateway_text = str(proposal.get("gateway_text") or "").strip()
    if not gateway_text:
        raise core.HTTPException(status_code=409, detail="proposta AI não é acionável")

    expected_world = _expected_world_from_proposal(proposal)
    context_ref = dict(proposal.get("context") or {})
    try:
        response = await core.process_gateway_payload({
            "source": "agent",
            "source_event_id": f"ai-proposal-{proposal_id}",
            "actor_id": str(proposal.get("actor_id") or "ai-router"),
            "display_name": proposal.get("display_name") or "AI Router",
            "kind": "text",
            "text": gateway_text,
            "metadata": {
                "ai_proposal_id": proposal_id,
                "ai_model": proposal.get("model"),
                "ai_confidence": proposal.get("confidence"),
                "original_source": proposal.get("source"),
                "context_digest": context_ref.get("digest"),
                "context_world_version": context_ref.get("world_version"),
                "context_world_sequence": context_ref.get("world_sequence"),
                "_context_expected_world": expected_world,
                **dict(proposal.get("metadata") or {}),
            },
        })
    except StaleContextError as exc:
        stale = await _mark_stale(proposal_id, exc)
        return JSONResponse({
            "ok": False,
            "world_mutated": False,
            "stale_context": True,
            "expected_world": exc.expected,
            "current_world": exc.current,
            "proposal": stale,
        }, status_code=409)

    if response.status_code < 300:
        payload = json.loads(response.body.decode("utf-8")) if response.body else {}
        world_event_id = (payload.get("event") or {}).get("event_id")
        async with core.ai_lock:
            committed = core.ai_proposals.mark_committed(proposal_id, world_event_id=world_event_id)
        await core.broadcast({"type": "ai_proposal", "proposal": committed})
    return response


async def _audience_ai_fallback(normalized: Any, original: Any):
    await main_spatial._observe_unhandled_audience(normalized)
    status = core.integrations.public_status()
    openai_ready = bool((status.get("openai") or {}).get("configured"))
    if not openai_ready or not main_spatial._audience_command_like(normalized.text):
        return JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "not_needed" if openai_ready else "not_configured",
        }, status_code=202)

    try:
        package = await compile_ai_context(
            source=normalized.source,
            actor_id=normalized.actor.actor_id,
        )
        router = core.build_ai_router()
        proposal = await asyncio.to_thread(
            router.propose,
            normalized.text,
            context=package.to_dict(),
        )
    except (core.AIRouterError, core.HTTPException) as exc:
        return JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "error",
            "ai_error": str(getattr(exc, "detail", exc)),
        }, status_code=202)

    proposal_dict = proposal.to_dict()
    actionable = bool(proposal.actionable and proposal.confidence >= core.AI_MIN_CONFIDENCE)
    async with core.ai_lock:
        stored = core.ai_proposals.create(
            action=proposal.action,
            confidence=proposal.confidence,
            reason=proposal.reason,
            original_text=proposal.original_text,
            model=proposal.model,
            gateway_text=proposal_dict.get("gateway_text") if actionable else None,
            actionable=actionable,
            source=normalized.source,
            actor_id=normalized.actor.actor_id,
            display_name=normalized.actor.display_name,
            metadata={"audience_fallback": True, **dict(normalized.metadata)},
            **_context_store_fields(package),
        )
    await core.broadcast({"type": "ai_proposal", "proposal": stored})

    action = str(stored.get("action") or "")
    gateway_text = str(stored.get("gateway_text") or "").strip()
    if stored.get("status") != "pending" or action not in main_spatial._AUDIENCE_AUTO_ACTIONS or not gateway_text:
        return JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "proposal_only",
            "proposal": stored,
        }, status_code=202)

    expected_world = _expected_world_from_proposal(stored)
    context_ref = dict(stored.get("context") or {})
    metadata = {
        **dict(normalized.metadata),
        "ai_proposal_id": stored["proposal_id"],
        "ai_auto_approved": True,
        "ai_model": stored.get("model"),
        "ai_confidence": stored.get("confidence"),
        "original_text": normalized.text,
        "context_digest": context_ref.get("digest"),
        "context_world_version": context_ref.get("world_version"),
        "context_world_sequence": context_ref.get("world_sequence"),
        "_context_expected_world": expected_world,
    }
    try:
        response = await original({
            "source": normalized.source,
            "source_event_id": f"{normalized.source_event_id}:ai",
            "actor_id": normalized.actor.actor_id,
            "display_name": normalized.actor.display_name,
            "kind": "text",
            "text": gateway_text,
            "metadata": metadata,
        })
    except StaleContextError as exc:
        stale = await _mark_stale(str(stored["proposal_id"]), exc)
        return JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "stale_rejected",
            "proposal": stale,
            "expected_world": exc.expected,
            "current_world": exc.current,
        }, status_code=202)

    if response.status_code < 300:
        body = json.loads(response.body.decode("utf-8")) if response.body else {}
        world_event_id = str((body.get("event") or {}).get("event_id") or "") or None
        async with core.ai_lock:
            committed = core.ai_proposals.mark_committed(
                str(stored["proposal_id"]),
                world_event_id=world_event_id,
            )
        await core.broadcast({"type": "ai_proposal", "proposal": committed})
        body["ai_fallback"] = "auto_committed"
        body["ai_proposal"] = committed
        return JSONResponse(body, status_code=response.status_code)
    return response


main_spatial._audience_ai_fallback = _audience_ai_fallback


_original_health = core.health


async def context_health() -> JSONResponse:
    response = await _original_health()
    payload = json.loads(response.body.decode("utf-8")) if response.body else {}
    pipeline = list(payload.get("pipeline") or [])
    if "context-compiler" not in pipeline:
        try:
            index = pipeline.index("ai-router")
        except ValueError:
            index = len(pipeline)
        pipeline.insert(index, "context-compiler")
    payload["pipeline"] = pipeline
    payload["context_compiler"] = {
        "enabled": True,
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "max_entities": context_compiler.max_entities,
        "max_regions": context_compiler.max_regions,
        "cold_world_bounded": True,
        "stale_guard": True,
        "actor_state_from_agent_output": False,
    }
    ai_current = core.ai_proposals.current()
    ai_router = dict(payload.get("ai_router") or {})
    ai_router["stale_total"] = sum(1 for row in ai_current if row.get("status") == "stale")
    payload["ai_router"] = ai_router
    return JSONResponse(payload, status_code=response.status_code)


def _replace_route(path: str, method: str, endpoint: Any) -> None:
    wanted = method.upper()
    for route in app.router.routes:
        if not isinstance(route, APIRoute):
            continue
        if route.path != path or wanted not in (route.methods or set()):
            continue
        route.endpoint = endpoint
        route.dependant.call = endpoint
        return
    raise RuntimeError(f"route not found: {method} {path}")


_replace_route("/api/ai/proposals", "POST", create_ai_proposal)
_replace_route("/api/ai/proposals/{proposal_id}/commit", "POST", commit_ai_proposal)
_replace_route("/api/health", "GET", context_health)
