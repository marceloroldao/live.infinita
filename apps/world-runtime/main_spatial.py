from __future__ import annotations

import asyncio
import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.routing import WebSocketRoute

import main as core
from cold_engine import ColdAuthoritativeWorldEngine
from mutation_gate_service import GuardedMutationService
from packages.spatial import FileRegionColdStore, MutationPrincipal
from proposal_ledger_runtime import install_runtime_proposal_ledger
from spatial_session import SpatialSession

app = core.app
_operator_approval_context: ContextVar[bool] = ContextVar("operator_approval_context", default=False)
_AUDIENCE_SOURCES = frozenset({"tiktok", "youtube"})
_AUDIENCE_AUTO_ACTIONS = frozenset({
    "spawn_person",
    "move_tree",
    "toggle_fire",
    "nov_to_fire",
    "nov_to_shelter",
    "nov_to_forest",
    "nov_explore",
})
_AI_TRIGGER_TERMS = (
    "nov", "fogueira", "fogo", "arvore", "árvore", "abrigo", "floresta",
    "explor", "andar", "caminh", "passe", "visitante", "personagem",
)


@app.middleware("http")
async def audience_proposal_commit_requires_operator(request, call_next):
    """Legacy audience commit endpoint is an operator approval boundary."""
    path = request.url.path
    is_audience_commit = (
        request.method.upper() == "POST"
        and path.startswith("/api/audience/proposals/")
        and path.endswith("/commit")
    )
    if not is_audience_commit:
        return await call_next(request)
    if not core.OPERATOR_TOKEN:
        return core.JSONResponse({"detail": "chave do operador não configurada"}, status_code=503)
    expected = f"Bearer {core.OPERATOR_TOKEN}".encode("utf-8")
    supplied = (request.headers.get("authorization") or "").encode("utf-8")
    if not core.secrets.compare_digest(supplied, expected):
        return core.JSONResponse(
            {"detail": "chave do operador inválida"},
            status_code=401,
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = _operator_approval_context.set(True)
    try:
        return await call_next(request)
    finally:
        _operator_approval_context.reset(token)


def _cold_store_root() -> Path | None:
    value = str(os.getenv("LIVE_INFINITA_COLD_STORE_DIR", "")).strip()
    return Path(value) if value else None


def _world_data_root() -> Path:
    value = str(os.getenv("LIVE_INFINITA_WORLD_DATA_DIR", "")).strip()
    return Path(value) if value else core.DATA_DIR


def _cold_engine_enabled() -> bool:
    return str(os.getenv("LIVE_INFINITA_COLD_ENGINE", "")).strip().lower() in {"1", "true", "yes", "on"}


def _configure_authoritative_engine() -> FileRegionColdStore | None:
    store_root = _cold_store_root()
    if not _cold_engine_enabled():
        if store_root is not None and (store_root / "manifest.json").exists():
            return FileRegionColdStore(store_root)
        return None
    if store_root is None:
        raise RuntimeError("LIVE_INFINITA_COLD_ENGINE requires LIVE_INFINITA_COLD_STORE_DIR")

    bootstrap_value = str(os.getenv("LIVE_INFINITA_COLD_BOOTSTRAP_FILE", "")).strip()
    bootstrap = Path(bootstrap_value) if bootstrap_value else (
        core.ROOT / "examples" / "world-state.mvp001.regional.bootstrap.json"
    )
    if not bootstrap.exists():
        raise RuntimeError(f"cold bootstrap not found: {bootstrap}")

    store = FileRegionColdStore(store_root)
    core.engine = ColdAuthoritativeWorldEngine(bootstrap, _world_data_root(), store)
    return store


def _principal_for_action(source: str, context: dict[str, Any] | None) -> MutationPrincipal:
    context = context or {}
    metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
    actor_id = str(context.get("actor_id") or "unknown").strip() or "unknown"
    normalized_source = str(source or "runtime").strip().lower() or "runtime"

    if actor_id == "system":
        authority = "system"
    elif metadata.get("ai_auto_approved") or metadata.get("audience_auto_approved"):
        # A closed allowlist was already validated in the gateway. The LLM only
        # interpreted intent; mutation still passes through this deterministic gate.
        authority = "world_agent"
    elif metadata.get("ai_proposal_id"):
        # Non-auto AI proposals only reach this path after explicit operator commit.
        authority = "operator"
    elif metadata.get("operator_approved") and metadata.get("proposal_id"):
        # Marker can only be injected inside the authenticated approval context.
        authority = "operator"
    elif metadata.get("proposal_id") or metadata.get("rule_id"):
        # Audience aggregation remains proposal-only until explicit approval.
        authority = "audience"
    elif normalized_source in {"tiktok", "youtube"}:
        authority = "audience"
    else:
        authority = "observer"

    return MutationPrincipal(
        source=normalized_source,
        actor_id=actor_id,
        authority=authority,
        subject_entity_id=None,
    )


def _nov_action(engine: ColdAuthoritativeWorldEngine, action: str) -> tuple[list[dict[str, Any]], str]:
    nov = engine.cold_store.get_entity("nov")
    if not isinstance(nov, dict):
        raise ValueError("nov não existe")

    target_id = {
        "nov_to_fire": "fire_01",
        "nov_to_shelter": "shelter_marker",
        "nov_to_forest": "ancient_tree",
    }.get(action)

    if action == "nov_explore":
        region_id = str(nov.get("region_id") or "")
        target_id = {
            "clearing": "ancient_tree",
            "deep_forest": "shelter_marker",
            "shelter": "fire_01",
        }.get(region_id, "ancient_tree")

    if not target_id:
        raise ValueError(f"ação de Nov desconhecida: {action}")
    target = engine.cold_store.get_entity(target_id)
    if not isinstance(target, dict):
        raise ValueError(f"destino de Nov não existe: {target_id}")
    position = target.get("position") if isinstance(target.get("position"), dict) else {}
    region_id = str(target.get("region_id") or "").strip()
    if not region_id:
        raise ValueError(f"destino sem região: {target_id}")
    operation = {
        "op": "move",
        "entity_id": "nov",
        "position": {"x": float(position.get("x", 0.0)), "y": float(position.get("y", 0.0))},
        "region_id": region_id,
    }
    label = str((target.get("properties") or {}).get("label") or target_id)
    narration = (
        "Nov escolhe um novo caminho e continua explorando."
        if action == "nov_explore"
        else f"Nov caminha em direção a {label}."
    )
    return [operation], narration


def _install_cold_mutation_gate() -> None:
    if not isinstance(core.engine, ColdAuthoritativeWorldEngine):
        return

    engine = core.engine
    guarded = GuardedMutationService(
        engine,
        decision_log_file=core.DATA_DIR / "mutation-decisions.jsonl",
    )

    def guarded_commit_action(
        action: str,
        source: str = "runtime",
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if action in {"nov_to_fire", "nov_to_shelter", "nov_to_forest", "nov_explore"}:
            operations, narration = _nov_action(engine, action)
        else:
            world = engine.load_world()
            _event, proposed_delta = engine.propose(world, action, source=source, context=context)
            operations = list(proposed_delta.get("operations", []))
            narration = str(proposed_delta.get("narration", ""))

        principal = _principal_for_action(source, context)
        result = guarded.commit(
            operations,
            principal=principal,
            context={
                **dict(context or {}),
                "validated_action": action,
                "proposal_narration": narration,
            },
            narration=narration,
        )
        if not result["ok"]:
            decision = result["decision"]
            raise ValueError(f"mutation rejected by policy: {decision['reason']}")
        return result["event"], result["delta"], result["world"]

    engine.commit_action = guarded_commit_action  # type: ignore[method-assign]


def _audience_command_like(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    return bool(lowered) and any(term in lowered for term in _AI_TRIGGER_TERMS)


async def _observe_unhandled_audience(normalized: Any) -> None:
    await core.observe_actor(
        source=normalized.source,
        actor_id=normalized.actor.actor_id,
        display_name=normalized.actor.display_name,
        kind=normalized.kind,
        source_event_id=normalized.source_event_id,
        metadata={"channel": "gateway", "unhandled": True, **dict(normalized.metadata)},
        observed_at_unix=core.time.time(),
    )


async def _audience_ai_fallback(normalized: Any, original: Any):
    await _observe_unhandled_audience(normalized)
    status = core.integrations.public_status()
    openai_ready = bool((status.get("openai") or {}).get("configured"))
    if not openai_ready or not _audience_command_like(normalized.text):
        return core.JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "not_needed" if openai_ready else "not_configured",
        }, status_code=202)

    try:
        router = core.build_ai_router()
        proposal = await asyncio.to_thread(router.propose, normalized.text)
    except (core.AIRouterError, core.HTTPException) as exc:
        return core.JSONResponse({
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
        )
    await core.broadcast({"type": "ai_proposal", "proposal": stored})

    action = str(stored.get("action") or "")
    gateway_text = str(stored.get("gateway_text") or "").strip()
    if stored.get("status") != "pending" or action not in _AUDIENCE_AUTO_ACTIONS or not gateway_text:
        return core.JSONResponse({
            "ok": True,
            "world_mutated": False,
            "audience_comment": "observed",
            "ai_fallback": "proposal_only",
            "proposal": stored,
        }, status_code=202)

    metadata = {
        **dict(normalized.metadata),
        "ai_proposal_id": stored["proposal_id"],
        "ai_auto_approved": True,
        "ai_model": stored.get("model"),
        "ai_confidence": stored.get("confidence"),
        "original_text": normalized.text,
    }
    response = await original({
        "source": normalized.source,
        "source_event_id": f"{normalized.source_event_id}:ai",
        "actor_id": normalized.actor.actor_id,
        "display_name": normalized.actor.display_name,
        "kind": "text",
        "text": gateway_text,
        "metadata": metadata,
    })
    if response.status_code < 300:
        body = json.loads(response.body.decode("utf-8")) if response.body else {}
        world_event_id = str((body.get("event") or {}).get("event_id") or "") or None
        async with core.ai_lock:
            committed = core.ai_proposals.mark_committed(str(stored["proposal_id"]), world_event_id=world_event_id)
        await core.broadcast({"type": "ai_proposal", "proposal": committed})
        body["ai_fallback"] = "auto_committed"
        body["ai_proposal"] = committed
        return core.JSONResponse(body, status_code=response.status_code)
    return response


def _install_operator_approval_marker() -> None:
    original = core.process_gateway_payload

    async def wrapped(payload: dict[str, Any]):
        cloned = dict(payload)
        metadata = dict(cloned.get("metadata") or {})
        source = str(cloned.get("source") or "").strip().lower()

        if (
            _operator_approval_context.get()
            and source == "api"
            and str(cloned.get("actor_id") or "").strip() == "audience-aggregator"
            and metadata.get("proposal_id")
        ):
            metadata["operator_approved"] = True
            cloned["metadata"] = metadata
            return await original(cloned)

        if source in _AUDIENCE_SOURCES:
            try:
                normalized, proposed, validation = core.pipeline.process(cloned)
            except ValueError:
                return await original(cloned)

            if validation.accepted and validation.action in _AUDIENCE_AUTO_ACTIONS:
                metadata["audience_auto_approved"] = True
                cloned["metadata"] = metadata
                return await original(cloned)

            if not validation.accepted and normalized.kind == "text":
                return await _audience_ai_fallback(normalized, original)

            if validation.accepted:
                await _observe_unhandled_audience(normalized)
                return core.JSONResponse({
                    "ok": True,
                    "world_mutated": False,
                    "audience_comment": "observed",
                    "requires_operator": True,
                    "proposed_action": proposed.action,
                }, status_code=202)

        return await original(cloned)

    core.process_gateway_payload = wrapped


cold_store = _configure_authoritative_engine()
_install_cold_mutation_gate()
_install_operator_approval_marker()
proposal_ledger = install_runtime_proposal_ledger(core, core.DATA_DIR)
spatial_session = SpatialSession(cold_store=cold_store) if cold_store is not None else SpatialSession()
session_views: dict[WebSocket, dict[str, Any]] = {}
_external_world_sync_task: asyncio.Task[None] | None = None
_last_world_marker: tuple[int, str] | None = None


def _world_marker(world: dict[str, Any]) -> tuple[int, str]:
    return int(world.get("sequence", 0)), str(world.get("state_hash") or "")


def _external_world_sync_seconds() -> float:
    raw = str(os.getenv("LIVE_INFINITA_EXTERNAL_WORLD_SYNC_MS", "500")).strip()
    try:
        milliseconds = max(100, int(raw))
    except ValueError:
        milliseconds = 500
    return milliseconds / 1000.0


async def spatial_broadcast(message: dict[str, Any]) -> None:
    """Broadcast side-channel messages unchanged and world state as local slices."""
    global _last_world_marker
    if message.get("type") == "world_state" and isinstance(message.get("world"), dict):
        _last_world_marker = _world_marker(message["world"])

    dead: list[WebSocket] = []
    for client, view in list(session_views.items()):
        try:
            payload = spatial_session.wrap_world_message(message, view)
            await client.send_json(payload)
        except Exception:
            dead.append(client)
    for client in dead:
        session_views.pop(client, None)


async def _external_world_sync_loop() -> None:
    """Project commits made by the autonomous writer into every live WebSocket."""
    global _last_world_marker
    interval = _external_world_sync_seconds()
    while True:
        try:
            world = core.engine.load_world()
            marker = _world_marker(world)
            if _last_world_marker is None:
                _last_world_marker = marker
            elif marker != _last_world_marker:
                refresh = getattr(cold_store, "refresh_manifest", None)
                if callable(refresh):
                    refresh()
                await spatial_broadcast({"type": "world_state", "world": world})
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(interval)


async def _start_external_world_sync() -> None:
    global _external_world_sync_task, _last_world_marker
    _last_world_marker = _world_marker(core.engine.load_world())
    if _external_world_sync_task is None or _external_world_sync_task.done():
        _external_world_sync_task = asyncio.create_task(
            _external_world_sync_loop(),
            name="live-infinita-external-world-sync",
        )


async def _stop_external_world_sync() -> None:
    global _external_world_sync_task
    task = _external_world_sync_task
    _external_world_sync_task = None
    if task is None:
        return
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def spatial_websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    world = core.engine.load_world()
    view = spatial_session.default_view(world)
    session_views[websocket] = view
    await websocket.send_json(spatial_session.wrap_world_message(
        {"type": "world_state", "world": world},
        view,
    ))
    try:
        while True:
            message = await websocket.receive_json()
            message_type = str(message.get("type", ""))
            if message_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            if message_type == "interest_update":
                view = spatial_session.normalize_view(message, view)
                session_views[websocket] = view
                world = core.engine.load_world()
                await websocket.send_json(spatial_session.wrap_world_message(
                    {"type": "world_state", "world": world},
                    view,
                ))
    except WebSocketDisconnect:
        session_views.pop(websocket, None)
    except Exception:
        session_views.pop(websocket, None)
        try:
            await websocket.close()
        except Exception:
            pass


def _replace_world_websocket_route() -> None:
    for index, route in enumerate(list(app.router.routes)):
        if isinstance(route, WebSocketRoute) and route.path == "/ws":
            app.router.routes[index] = WebSocketRoute("/ws", spatial_websocket_endpoint)
            return
    raise RuntimeError("world websocket route /ws not found")


core.broadcast = spatial_broadcast
_replace_world_websocket_route()
app.add_event_handler("startup", _start_external_world_sync)
app.add_event_handler("shutdown", _stop_external_world_sync)
