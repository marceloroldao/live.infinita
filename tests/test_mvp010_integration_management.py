import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import test_mvp008_actor_api as actor_api_tests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "integrations"))
from settings import IntegrationStore


class IntegrationStoreTest(unittest.TestCase):
    def test_update_retains_omitted_secrets_masks_and_clears_explicit_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "integrations.json"
            store = IntegrationStore(path)
            store.update({"openai_api_key": "sk-secret-1234", "openai_model": "gpt-5-mini"})
            store.update({"tiktok_unique_id": "@live", "openai_api_key": None})
            self.assertEqual(store.load()["openai_api_key"], "sk-secret-1234")
            status = store.public_status()
            self.assertEqual(status["openai"]["key_hint"], "••••1234")
            self.assertNotIn("sk-secret", json.dumps(status))
            store.update({"openai_api_key": ""})
            self.assertNotIn("openai_api_key", store.load())
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)


class IntegrationManagementAPITest(unittest.TestCase):
    def setUp(self):
        actor_api_tests.ActorAPITest.setUp(self)
        self.enterContext(patch.object(self.runtime, "OPERATOR_TOKEN", "manager-token"))
        self.headers = {"Authorization": "Bearer manager-token"}

    def test_manager_page_and_api_authentication(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Live Infinita", page.text)
        self.assertIn("login-form", page.text)
        self.assertEqual(page.headers["cache-control"], "no-store")
        self.assertIn("frame-ancestors 'none'", page.headers["content-security-policy"])
        self.assertEqual(self.client.get("/api/manage/integrations").status_code, 401)
        self.assertEqual(self.client.put("/api/manage/integrations", json={}).status_code, 401)

    def test_save_masks_and_never_returns_secrets(self):
        secret_openai = "sk-super-secret-9876"
        secret_tiktok = "euler-secret-4567"
        response = self.client.put("/api/manage/integrations", headers=self.headers, json={
            "openai_api_key": secret_openai, "openai_model": "gpt-5-mini",
            "tiktok_unique_id": "live.user", "tiktok_sign_api_key": secret_tiktok,
        })
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(secret_openai, response.text)
        self.assertNotIn(secret_tiktok, response.text)
        status = self.client.get("/api/manage/integrations", headers=self.headers)
        self.assertEqual(status.json()["tiktok"]["unique_id"], "@live.user")
        self.assertEqual(status.json()["tiktok"]["apply_mode"], "automatic-service-restart")
        self.assertNotIn(secret_openai, status.text)
        health = self.client.get("/api/health")
        self.assertEqual(health.json()["integrations"], {"openai": True, "tiktok": True})
        self.assertNotIn(secret_openai, health.text)
        self.assertEqual(self.client.get("/api/world").status_code, 200)
        self.assertTrue(self.client.get("/api/replay/verify").json()["ok"])

    def test_blank_secret_explicitly_removes_it(self):
        self.runtime.integrations.update({"openai_api_key": "sk-existing"})
        response = self.client.put("/api/manage/integrations", headers=self.headers,
                                   json={"openai_api_key": ""})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["integrations"]["openai"]["configured"])

    def test_openai_connection_uses_bearer_and_sanitizes_errors(self):
        self.runtime.integrations.update({"openai_api_key": "sk-test-secret", "openai_model": "gpt-5-mini"})
        response = MagicMock()
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        response.read.return_value = json.dumps({"data": [{"id": "gpt-5-mini"}]}).encode()
        with patch.object(self.runtime.urllib.request, "urlopen", return_value=response) as call:
            result = self.client.post("/api/manage/integrations/openai/test", headers=self.headers)
        self.assertEqual(result.status_code, 200)
        request = call.call_args.args[0]
        self.assertEqual(request.headers["Authorization"], "Bearer sk-test-secret")
        self.assertTrue(result.json()["selected_model_available"])
        error = self.runtime.urllib.error.HTTPError("url", 401, "contains sk-test-secret", {}, None)
        with patch.object(self.runtime.urllib.request, "urlopen", side_effect=error):
            refused = self.client.post("/api/manage/integrations/openai/test", headers=self.headers)
        self.assertEqual(refused.status_code, 422)
        self.assertNotIn("sk-test-secret", refused.text)

    def test_input_validation_rejects_invalid_names(self):
        for payload in ({"openai_model": "bad model"}, {"tiktok_unique_id": "bad user!"}):
            self.assertEqual(self.client.put("/api/manage/integrations", headers=self.headers,
                                             json=payload).status_code, 422)


if __name__ == "__main__":
    unittest.main()
