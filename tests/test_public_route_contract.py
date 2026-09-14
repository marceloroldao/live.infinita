from pathlib import Path
import unittest

from starlette.routing import Mount


ROOT = Path(__file__).resolve().parents[1]


async def _dummy_asgi(scope, receive, send):
    return None


class PublicRouteContractTests(unittest.TestCase):
    def test_public_route_contract_is_preserved(self) -> None:
        wrapper = (ROOT / "apps" / "world-runtime" / "main_live.py").read_text(encoding="utf-8")
        manager = (ROOT / "apps" / "manager" / "index.html").read_text(encoding="utf-8")
        legacy_renderer = (ROOT / "apps" / "renderer-web" / "index.html").read_text(encoding="utf-8")

        self.assertIn('"/gdscript"', wrapper)
        self.assertIn('name="gdscript-renderer"', wrapper)
        self.assertIn('name="manager"', wrapper)
        self.assertIn('RedirectResponse(url="/", status_code=308)', wrapper)

        self.assertIn('href="/godot/"', manager)
        self.assertIn('href="/gdscript/"', manager)
        self.assertIn('src="/app.js"', manager)
        self.assertIn('src="/gdscript/app.js"', legacy_renderer)

    def test_starlette_root_mount_is_empty_and_wrapper_removes_it(self) -> None:
        # This is the exact regression that let the MVP-001 catch-all shadow '/'.
        root_mount = Mount("/", app=_dummy_asgi)
        self.assertEqual(root_mount.path, "")
        wrapper = (ROOT / "apps" / "world-runtime" / "main_live.py").read_text(encoding="utf-8")
        self.assertIn('route.path in {"", "/", "/manage"}', wrapper)

    def test_production_unit_preserves_wrapper_chain_to_public_routes(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
        cognitive = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")
        context = (ROOT / "apps" / "world-runtime" / "main_context_live.py").read_text(encoding="utf-8")

        self.assertIn("main_cognitive_live:app", unit)
        self.assertIn("import main_context_live", cognitive)
        self.assertIn("app = main_context_live.app", cognitive)
        self.assertIn("import main_live", context)
        self.assertIn("app = main_live.app", context)


if __name__ == "__main__":
    unittest.main()
