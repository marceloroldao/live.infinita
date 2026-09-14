from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

import main as core
import main_spatial

app = main_spatial.app


def _looks_internal_narration(text: str) -> bool:
    value = text.strip().lower()
    return (
        value.startswith("plan plan_")
        or value.startswith("intent-plan step ")
        or (value.startswith("plan ") and " revision " in value and " step " in value)
    )


def _sanitize_public_world_message(message: dict[str, Any]) -> dict[str, Any]:
    """Never expose execution/audit strings through the live presentation stream."""
    result = deepcopy(message)
    world = result.get("world")
    if not isinstance(world, dict):
        return result
    narration = world.get("narration")
    if not isinstance(narration, dict):
        return result
    text = str(narration.get("text") or "")
    if _looks_internal_narration(text):
        world["narration"] = {
            **narration,
            "text": "Nov continua sua jornada pelo mundo.",
        }
    return result


# main_spatial projects the authoritative world into observer-local slices.
# Wrap that final presentation boundary so both Godot and the narrator consume
# clean narrative text, including already-persisted legacy plan messages.
_original_wrap_world_message = main_spatial.spatial_session.wrap_world_message


def _public_wrap_world_message(message: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    projected = _original_wrap_world_message(message, view)
    return _sanitize_public_world_message(projected)


main_spatial.spatial_session.wrap_world_message = _public_wrap_world_message  # type: ignore[method-assign]


# Restore the public presentation contract introduced by manager-shell-011 while
# keeping main_spatial as the authoritative runtime implementation.
#
#   /           -> Manager
#   /manage[/]  -> legacy redirect to /
#   /gdscript/  -> legacy renderer / GDScript preview
#   /godot/     -> served by nginx from the Godot Web export
#
# main.py still carries legacy mounts for compatibility with older entrypoints.
# This production wrapper removes only those two static mounts and reattaches
# them in the intended order so the catch-all root cannot shadow /gdscript.
app.router.routes = [
    route
    for route in app.router.routes
    if not (isinstance(route, Mount) and route.path in {"/", "/manage"})
]


@app.get("/manage", include_in_schema=False)
@app.get("/manage/", include_in_schema=False)
async def legacy_manager_redirect() -> RedirectResponse:
    return RedirectResponse(url="/", status_code=308)


@app.middleware("http")
async def manager_shell_security_headers(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path == "/" or path in {"/app.js", "/style.css", "/visibility.css"}:
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'"
        )
    return response


app.mount(
    "/gdscript",
    StaticFiles(directory=str(Path(core.RENDERER_DIR)), html=True),
    name="gdscript-renderer",
)
app.mount(
    "/",
    StaticFiles(directory=str(Path(core.MANAGER_DIR)), html=True),
    name="manager",
)
