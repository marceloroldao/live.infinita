from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_public_route_contract_is_preserved() -> None:
    wrapper = (ROOT / "apps" / "world-runtime" / "main_live.py").read_text(encoding="utf-8")
    manager = (ROOT / "apps" / "manager" / "index.html").read_text(encoding="utf-8")
    legacy_renderer = (ROOT / "apps" / "renderer-web" / "index.html").read_text(encoding="utf-8")

    assert '"/gdscript"' in wrapper
    assert 'name="gdscript-renderer"' in wrapper
    assert 'name="manager"' in wrapper
    assert 'RedirectResponse(url="/", status_code=308)' in wrapper

    assert 'href="/godot/"' in manager
    assert 'href="/gdscript/"' in manager
    assert 'src="/app.js"' in manager
    assert 'src="/gdscript/app.js"' in legacy_renderer


def test_production_unit_uses_public_route_wrapper() -> None:
    unit = (ROOT / "deploy" / "live-infinita.service").read_text(encoding="utf-8")
    assert "main_live:app" in unit
