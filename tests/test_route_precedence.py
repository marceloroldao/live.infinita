from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "apps" / "world-runtime" / "route_precedence.py"
spec = importlib.util.spec_from_file_location("route_precedence", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec and spec.loader
sys.modules[spec.name] = module
spec.loader.exec_module(module)
promote_api_route_before_root = module.promote_api_route_before_root


class RoutePrecedenceTests(unittest.TestCase):
    def test_late_api_route_moves_before_root_static_mount(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("manager", encoding="utf-8")
            app = FastAPI()
            app.mount("/", StaticFiles(directory=directory, html=True), name="manager")

            @app.get("/api/extension")
            async def extension():
                return {"ok": True}

            routes = app.router.routes
            api = next(
                route for route in routes
                if isinstance(route, APIRoute) and route.path == "/api/extension"
            )
            root = next(
                route for route in routes
                if isinstance(route, Mount) and route.path in {"", "/"}
            )
            self.assertGreater(routes.index(api), routes.index(root))

            promote_api_route_before_root(app, "/api/extension")

            routes = app.router.routes
            self.assertLess(routes.index(api), routes.index(root))

    def test_already_correct_route_order_is_stable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "index.html").write_text("manager", encoding="utf-8")
            app = FastAPI()

            @app.get("/api/extension")
            async def extension():
                return {"ok": True}

            app.mount("/", StaticFiles(directory=directory, html=True), name="manager")
            before = list(app.router.routes)
            promote_api_route_before_root(app, "/api/extension")
            self.assertEqual(before, app.router.routes)

    def test_without_root_mount_route_is_unchanged(self) -> None:
        app = FastAPI()

        @app.get("/api/extension")
        async def extension():
            return {"ok": True}

        before = list(app.router.routes)
        promote_api_route_before_root(app, "/api/extension")
        self.assertEqual(before, app.router.routes)

    def test_unknown_extension_fails_closed(self) -> None:
        app = FastAPI()
        with self.assertRaisesRegex(RuntimeError, "API extension route not found"):
            promote_api_route_before_root(app, "/api/missing")


if __name__ == "__main__":
    unittest.main()
