from __future__ import annotations

import asyncio
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
    elif metadata.get("ai_proposal_id"):
        # AI proposals only reach this path after the operator explicitly commits them.
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
        world = engine.load_world()
        _event, proposed_delta = engine.propose(world, action, source=source, context=context)
        principal = _principal_for_action(source, context)
        result = guarded.commit(
            list(proposed_delta.get("operations", [])),
            principal=principal,
            context={
                **dict(context or {}),
                "validated_action": action,
                "proposal_narration": proposed_delta.get("narration", ""),
            },
            narration=str(proposed_delta.get("narration", "")),
        )
        if not result["ok"]:
            decision = result["decision"]
            raise ValueError(f"mutation rejected by policy: {decision['reason']}")
        return result["event"], result["delta"], result["world"]

    engine.commit_action = guarded_commit_action  # type: ignore[method-assign]


def _install_operator_approval_marker() -> None:
    original = core.process_gateway_payload

    async def wrapped(payload: dict[str, Any]):
        cloned = dict(payload)
        metadata = dict(cloned.get("metadata") or {})
        if (
            _operator_approval_context.get()
            and str(cloned.get("source") or "").strip().lower() == "api"
            and str(cloned.get("actor_id") or "").strip() == "audience-aggregator"
            and metadata.get("proposal_id")
        ):
            metadata["operator_approved"] = True
            cloned["metadata"] = metadata
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
                await spatial_broadcast({"type": "world_state", "world": world})
        except asyncio.CancelledError:
            raise
        except Exception:
            # A transient atomic-replace/read race must not take down the runtime.
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
    global _last_world_marker
    await websocket.accept()
    world = core.engine.load_world()
    _last_world_marker = _world_marker(world)
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
                _last_world_marker = _world_marker(world)
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


# Existing runtime code resolves `broadcast` and `engine` from the `main` module
# globals at call time. Replacing those symbols keeps REST/API logic untouched
# while making delivery observer-local and, when opted in, cold-authoritative.
core.broadcast = spatial_broadcast
_replace_world_websocket_route()
app.add_event_handler("startup", _start_external_world_sync)
app.add_event_handler("shutdown", _stop_external_world_sync)
