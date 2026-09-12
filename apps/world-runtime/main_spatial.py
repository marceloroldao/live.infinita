from __future__ import annotations

from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.routing import WebSocketRoute

import main as core
from spatial_session import SpatialSession

app = core.app
spatial_session = SpatialSession()
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


# Existing runtime code resolves `broadcast` from the `main` module globals at call time,
# so replacing this symbol keeps REST/API logic untouched while making delivery observer-local.
core.broadcast = spatial_broadcast
_replace_world_websocket_route()
