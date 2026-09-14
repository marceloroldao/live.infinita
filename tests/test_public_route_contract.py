from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


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

    def test_production_unit_uses_public_route_wrapper(self) -> None:
        unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
        self.assertIn("main_live:app", unit)


if __name__ == "__main__":
    unittest.main()
