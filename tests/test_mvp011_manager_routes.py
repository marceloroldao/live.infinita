import unittest
from unittest.mock import patch

import test_mvp008_actor_api as actor_api_tests


class ManagerRoutesTest(unittest.TestCase):
    def setUp(self):
        actor_api_tests.ActorAPITest.setUp(self)
        self.enterContext(patch.object(self.runtime, "OPERATOR_TOKEN", "manager-password"))

    def test_login_creates_http_only_session_and_unlocks_manager_api(self):
        refused = self.client.post("/api/manage/login", json={"password": "wrong"})
        self.assertEqual(refused.status_code, 401)

        login = self.client.post("/api/manage/login", json={"password": "manager-password"})
        self.assertEqual(login.status_code, 200)
        cookie = login.headers["set-cookie"]
        self.assertIn("HttpOnly", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("SameSite=strict", cookie)
        session = login.cookies[self.runtime.SESSION_COOKIE]
        status = self.client.get(
            "/api/manage/integrations",
            headers={"Cookie": f"{self.runtime.SESSION_COOKIE}={session}"},
        )
        self.assertEqual(status.status_code, 200)

    def test_manager_is_root_and_renderers_have_stable_subpaths(self):
        root = self.client.get("/")
        self.assertEqual(root.status_code, 200)
        self.assertIn("Entrar no manager", root.text)
        self.assertIn("visibility.css", root.text)
        visibility = self.client.get("/visibility.css")
        self.assertIn("display: none !important", visibility.text)
        legacy = self.client.get("/manage/", follow_redirects=False)
        self.assertEqual(legacy.status_code, 308)
        self.assertEqual(legacy.headers["location"], "/")
        gdscript = self.client.get("/gdscript/")
        self.assertEqual(gdscript.status_code, 200)
        self.assertIn("/gdscript/app.js", gdscript.text)

    def test_expired_or_tampered_sessions_are_rejected(self):
        expired = self.runtime.session_value(1)
        tampered = expired[:-1] + ("0" if expired[-1] != "0" else "1")
        for session in (expired, tampered):
            response = self.client.get(
                "/api/manage/integrations",
                headers={"Cookie": f"{self.runtime.SESSION_COOKIE}={session}"},
            )
            self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
