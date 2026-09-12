from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.routing import WebSocketRoute

import main as core
from cold_engine import ColdAuthoritativeWorldEngine
from packages.spatial import FileRegionColdStore
from spatial_session import SpatialSession

app = core.app


def _cold_store_root() -> Path | None:
    value = str(os.getenv("LIVE_INFINITA_COLD_STORE_DIR", "")).strip()
    return Path(value) if value else None


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
    core.engine = ColdAuthoritativeWorldEngine(bootstrap, core.DATA_DIR, store)
    return store


cold_store = _configure_authoritative_engine()
spatial_session = SpatialSession(cold_store=cold_store) if cold_store is not None else SpatialSession()
session_views: dict[WebSocket, dict[str, Any]] = {}


async def spatial_broadcast(message: dict[str, Any]) -> None:
    """Broadcast side-channel messages unchanged and world state as local slices."""
    dead: list[WebSocket] = []
    for client, view in list(session_views.items()):
        try:
            payload = spatial_session.wrap_world_message(message, view)
            await client.send_json(payload)
        except Exception:
            dead.append(client)
    for client in dead:
        session_views.pop(client, None)


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
                await websocket.send_json(spatial_session.wrap_world_message(
                    {"type": "world_state", "world": core.engine.load_world()},
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
