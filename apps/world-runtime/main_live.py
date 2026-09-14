from __future__ import annotations

from pathlib import Path

from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.routing import Mount

import main as core
from main_spatial import app


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
