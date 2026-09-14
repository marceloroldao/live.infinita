from __future__ import annotations

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

app = main_spatial.app
APP_STARTED_AT = time.time()
TIKTOK_STATUS_FILE = core.DATA_DIR / "tiktok-status.json"


def _looks_internal_narration(text: str) -> bool:
    value = text.strip().lower()
    return (
        value.startswith("plan plan_")
        or value.startswith("intent-plan step ")
        or (value.startswith("plan ") and " revision " in value and " step " in value)
    )


def _sanitize_public_world_message(message: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(message)
    world = result.get("world")
    if not isinstance(world, dict):
        return result
    narration = world.get("narration")
    if not isinstance(narration, dict):
        return result
    text = str(narration.get("text") or "")
    if _looks_internal_narration(text):
        world["narration"] = {**narration, "text": "Nov continua sua jornada pelo mundo."}
    return result


_original_wrap_world_message = main_spatial.spatial_session.wrap_world_message


def _public_wrap_world_message(message: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    projected = _original_wrap_world_message(message, view)
    return _sanitize_public_world_message(projected)


main_spatial.spatial_session.wrap_world_message = _public_wrap_world_message  # type: ignore[method-assign]


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
            "period": (world.get("environment") or {}).get("period"),
            "replay_ok": bool(replay.get("ok")),
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
