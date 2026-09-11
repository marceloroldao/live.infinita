import json
import time
import unittest
from unittest.mock import patch

import test_mvp008_actor_api as actor_api_tests


class MonitoringAPITest(unittest.TestCase):
    def setUp(self):
        actor_api_tests.ActorAPITest.setUp(self)
        self.enterContext(patch.object(self.runtime, "OPERATOR_TOKEN", "monitor-token"))
        self.headers = {"Authorization": "Bearer monitor-token"}

    def test_monitor_requires_auth_and_returns_safe_operational_snapshot(self):
        self.runtime.integrations.update({
            "openai_api_key": "sk-never-expose-this",
            "openai_model": "gpt-5-mini",
            "tiktok_unique_id": "@live.user",
            "tiktok_sign_api_key": "never-expose-euler",
        })
        self.runtime.TIKTOK_STATUS_FILE.write_text(json.dumps({
            "state": "connected", "unique_id": "@live.user",
            "room_id": "123", "updated_at_unix": time.time(),
        }), encoding="utf-8")
        self.assertEqual(self.client.get("/api/manage/monitor").status_code, 401)
        response = self.client.get("/api/manage/monitor", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["runtime"]["state"], "online")
        self.assertEqual(body["tiktok"]["state"], "connected")
        self.assertFalse(body["tiktok"]["stale"])
        self.assertTrue(body["world"]["replay_ok"])
        self.assertIn("activity", body)
        self.assertNotIn("sk-never", response.text)
        self.assertNotIn("never-expose", response.text)

    def test_monitor_page_assets_are_available(self):
        page = self.client.get("/")
        self.assertIn("Visão geral", page.text)
        self.assertIn("monitoring.css", page.text)
        self.assertEqual(self.client.get("/monitoring.css").status_code, 200)


if __name__ == "__main__":
    unittest.main()
