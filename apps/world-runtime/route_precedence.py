from __future__ import annotations

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount


def promote_api_route_before_root(app: FastAPI, path: str) -> None:
    """Move one API route ahead of a root StaticFiles catch-all mount.

    Starlette resolves routes in declaration order. A StaticFiles mount at '/'
    is represented internally with an empty path and can shadow routes added by
    extension wrappers imported later. This helper makes that precedence
    explicit without disturbing the relative order of existing routes.
    """
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
