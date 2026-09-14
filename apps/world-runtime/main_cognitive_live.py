from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Depends
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.routing import Mount

import main as core
import main_context_live
import main_spatial
from memoria_v2_adapter import build_nov_cognitive_frame, to_memoria_v2_request_payload


app = main_context_live.app


def _flag_enabled(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


COGNITIVE_GYM_ENABLED = _flag_enabled("LIVE_INFINITA_MEMORIA_V2_COGNITIVE_GYM")


def _entity_map(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("id")): row
        for row in rows
        if isinstance(row, dict) and str(row.get("id") or "").strip()
    }


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


_original_context_health = main_context_live.context_health


async def cognitive_health() -> JSONResponse:
    response = await _original_context_health()
    payload = json.loads(response.body.decode("utf-8")) if response.body else {}
    payload["cognitive_gym_v2"] = {
        "enabled": COGNITIVE_GYM_ENABLED,
        "mode": "read-only-cognitive-projection",
        "direct_world_write": False,
        "observer": "nov",
        "contract": "CognitiveFrame -> Memoria V2 request payload",
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


def _promote_api_route_before_root(path: str) -> None:
    """Keep late extension routes ahead of the Manager catch-all mount at '/'."""
    routes = app.router.routes
    candidate = next(
        (route for route in routes if isinstance(route, APIRoute) and route.path == path),
        None,
    )
    if candidate is None:
        raise RuntimeError(f"API extension route not found: {path}")

    root_index = next(
        (
            index
            for index, route in enumerate(routes)
            if isinstance(route, Mount) and route.path in {"", "/"}
        ),
        None,
    )
    if root_index is None:
        return
    candidate_index = routes.index(candidate)
    if candidate_index < root_index:
        return
    routes.pop(candidate_index)
    root_index = next(
        index
        for index, route in enumerate(routes)
        if isinstance(route, Mount) and route.path in {"", "/"}
    )
    routes.insert(root_index, candidate)


# main_context_live is imported after main_live has mounted Manager at '/'. Its
# preview route and this cognitive route therefore need explicit precedence.
_promote_api_route_before_root("/api/ai/context/preview")
_promote_api_route_before_root("/api/cognitive/v2/frame")
