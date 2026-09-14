from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ManagerLiveSimulatorTests(unittest.TestCase):
    def test_manager_exposes_simulator_preview_and_audience_controls(self) -> None:
        html = (ROOT / "apps" / "manager" / "index.html").read_text(encoding="utf-8")
        self.assertIn('data-page="simulador"', html)
        self.assertIn('id="sim-godot-frame"', html)
        self.assertIn('src="/godot/?manager-simulator=1"', html)
        self.assertIn('id="sim-display-name"', html)
        self.assertIn('id="sim-actor-id"', html)
        self.assertIn('id="sim-comment"', html)
        self.assertIn('id="sim-new-viewer"', html)
        self.assertIn('id="sim-chat-feed"', html)

    def test_simulator_uses_protected_runtime_and_same_audience_policy(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")
        self.assertIn('@app.post("/api/manage/simulator/comment", dependencies=[Depends(core.require_operator)])', source)
        self.assertIn('@app.get("/api/manage/simulator/state", dependencies=[Depends(core.require_operator)])', source)
        self.assertIn('"source": "simulator"', source)
        self.assertIn('"manager_simulator": True', source)
        self.assertIn('main_spatial._AUDIENCE_AUTO_ACTIONS', source)
        self.assertIn('main_spatial._audience_ai_fallback', source)
        self.assertIn('main_live.story_narrator.render_interaction', source)
        self.assertIn('main_live._broadcast_story_cue(cue)', source)

    def test_simulator_is_blocked_during_fresh_real_tiktok_live(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")
        self.assertIn('status.get("state") == "connected" and fresh', source)
        self.assertIn('if live_active and not request.allow_during_live:', source)
        self.assertIn('simulador bloqueado para não misturar audiência real com teste', source)

    def test_manager_client_supports_multiple_viewers_and_narrator_reply(self) -> None:
        source = (ROOT / "apps" / "manager" / "simulator.js").read_text(encoding="utf-8")
        self.assertIn("api('/api/manage/simulator/comment'", source)
        self.assertIn("api('/api/manage/simulator/state')", source)
        self.assertIn('manager-viewer-', source)
        self.assertIn('data.narration_cue?.text', source)
        self.assertIn("'narrator'", source)
        self.assertIn("'Narrador'", source)
        self.assertIn('chooseNewViewer', source)

    def test_late_simulator_routes_are_promoted_before_manager_root_mount(self) -> None:
        source = (ROOT / "apps" / "world-runtime" / "main_cognitive_live.py").read_text(encoding="utf-8")
        self.assertIn('promote_api_route_before_root(app, "/api/manage/simulator/state")', source)
        self.assertIn('promote_api_route_before_root(app, "/api/manage/simulator/comment")', source)


if __name__ == "__main__":
    unittest.main()
