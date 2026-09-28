"""Production-composition smoke test using an isolated, disposable world directory."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PerformanceEndpointContract(unittest.TestCase):
    def test_real_story_app_route_and_auth_boundary(self) -> None:
        snippet = """
import json, os, time
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
import main_story_live
import main as core
from packages.observability import runtime_metrics

folder = Path(os.environ['LIVE_INFINITA_DATA_DIR'])
(folder / 'render-runtime-status.json').write_text(json.dumps({
    'updated_at_unix': time.time(), 'godot_fps': 12,
    'capture_fps': 15, 'governor_enabled': True,
}))
with patch.object(runtime_metrics, '_relay_health',
                  return_value={'available': True, 'active_streams': 1, 'max_clients': 4}):
    with TestClient(main_story_live.app) as client:
        unauth = client.get('/api/manage/performance')
        assert unauth.status_code == 503, unauth.status_code
        main_story_live.app.dependency_overrides[core.require_operator] = lambda: None
        response = client.get('/api/manage/performance')
        assert response.status_code == 200, response.text
        result = response.json()
        assert sorted(result) == ['api', 'audio', 'audio_web',
                                  'generated_at_unix', 'host', 'renderer']
        assert result['renderer']['available'] is True
        assert result['renderer']['fps'] == 12
        assert result['audio_web']['active_streams'] == 1
print('ISOLATED_MANAGER_PERFORMANCE_ROUTE_OK')
"""
        with tempfile.TemporaryDirectory(prefix="mvp016-contract-") as folder:
            env = os.environ.copy()
            env.update({
                "LIVE_INFINITA_DATA_DIR": folder,
                "LIVE_INFINITA_WORLD_DATA_DIR": folder,
                "LIVE_INFINITA_COLD_ENGINE": "0",
                "PYTHONPATH": os.pathsep.join((
                    str(ROOT), str(ROOT / "apps/world-runtime"),
                    str(ROOT / "apps/audio-service"),
                    str(ROOT / "apps/audience"),
                )),
            })
            env.pop("LIVE_INFINITA_COLD_STORE_DIR", None)
            env.pop("LIVE_INFINITA_OPERATOR_TOKEN", None)
            run = subprocess.run(
                [sys.executable, "-c", snippet], cwd=ROOT, env=env,
                text=True, capture_output=True, timeout=45, check=False,
            )
        self.assertEqual(run.returncode, 0, run.stderr + run.stdout)
        self.assertIn("ISOLATED_MANAGER_PERFORMANCE_ROUTE_OK", run.stdout)


if __name__ == "__main__":
    unittest.main()
