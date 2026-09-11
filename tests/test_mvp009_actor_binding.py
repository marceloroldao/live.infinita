from concurrent.futures import ThreadPoolExecutor
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
import test_mvp008_actor_api as actor_api_tests


class ActorBindingTest(unittest.TestCase):
    def setUp(self):
        actor_api_tests.ActorAPITest.setUp(self)
        self.enterContext(patch.object(self.runtime, "OPERATOR_TOKEN", "test-operator-token"))
        for source in ("tiktok", "youtube"):
            self.runtime.actors.observe(source=source, actor_id="alice", display_name="Alice",
                                        kind="join", source_event_id="first")
        self.runtime.engine.commit_action("spawn_person")
        self.headers = {"Authorization": "Bearer test-operator-token"}
        self.path = "/api/actors/tiktok/alice/entity"
        self.payload = {"entity_id": "person_01"}

    def bind(self, path=None, payload=None):
        return self.client.put(path or self.path, json=payload or self.payload, headers=self.headers)

    def unbind(self, entity_id="person_01"):
        return self.client.request("DELETE", self.path, json={"entity_id": entity_id}, headers=self.headers)

    def test_bind_unbind_preserve_world_observations_and_history(self):
        paths = [self.runtime.engine.world_file, self.runtime.engine.events_file,
                 self.runtime.engine.deltas_file, self.runtime.ACTOR_OBSERVATIONS_FILE]
        before = [p.read_bytes() for p in paths]
        self.assertTrue(self.bind().json()["changed"])
        self.assertFalse(self.bind().json()["changed"])
        # Simulate a store restart; no in-memory binding state is authoritative.
        self.runtime.bindings = self.runtime.ActorBindingStore(self.runtime.ACTOR_BINDINGS_FILE)
        actor = self.client.get("/api/actors/tiktok/alice").json()
        self.assertEqual((actor["entity_id"], actor["binding_status"]), ("person_01", "active"))
        listed = self.client.get("/api/actors").json()["actors"]
        self.assertEqual(next(a for a in listed if a["source"] == "tiktok")["entity_id"], "person_01")
        self.assertIsNone(self.client.get("/api/actors/youtube/alice").json()["entity_id"])
        self.assertTrue(self.unbind().json()["changed"])
        self.assertFalse(self.unbind().json()["changed"])
        history = self.client.get("/api/actors/tiktok/alice/bindings").json()["history"]
        self.assertEqual([r["operation"] for r in history], ["bind", "unbind"])
        self.assertEqual(history[0]["provenance"]["channel"], "operator-api")
        self.assertEqual([p.read_bytes() for p in paths], before)
        self.assertTrue(self.runtime.engine.verify_replay()["ok"])

    def test_other_actor_cannot_take_bound_character(self):
        self.assertEqual(self.bind().status_code, 200)
        self.assertEqual(self.bind("/api/actors/youtube/alice/entity").status_code, 409)
        self.assertTrue(self.unbind().json()["changed"])
        self.assertEqual(self.bind("/api/actors/youtube/alice/entity").status_code, 200)

    def test_actor_cannot_switch_without_unbinding(self):
        self.assertEqual(self.bind().status_code, 200)
        with self.assertRaises(self.runtime.BindingConflict):
            self.runtime.bindings.bind("tiktok:alice", "another-person")
        self.assertEqual(self.unbind("another-person").status_code, 409)
        self.assertEqual(self.runtime.bindings.current(), {"tiktok:alice": "person_01"})

    def test_unknown_actor_unknown_character_and_non_character_are_rejected(self):
        self.assertEqual(self.bind("/api/actors/tiktok/missing/entity").status_code, 404)
        self.assertEqual(self.bind(payload={"entity_id": "missing"}).status_code, 404)
        self.assertEqual(self.bind(payload={"entity_id": "tree_01"}).status_code, 422)
        self.assertEqual(self.bind(payload={"entity_id": " "}).status_code, 422)
        self.assertEqual(self.runtime.bindings.history(), [])

    def test_operator_key_required_for_both_writes(self):
        for method in ("PUT", "DELETE"):
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                response = self.client.request(method, self.path, json=self.payload, headers=headers)
                self.assertEqual(response.status_code, 401)
        self.assertEqual(self.runtime.bindings.history(), [])
        with patch.object(self.runtime, "OPERATOR_TOKEN", ""):
            self.assertEqual(self.bind().status_code, 503)

    def test_reset_keeps_binding_visible_and_allows_explicit_unbind(self):
        self.assertEqual(self.bind().status_code, 200)
        self.runtime.engine.commit_action("reset")
        actor = self.client.get("/api/actors/tiktok/alice").json()
        self.assertEqual((actor["entity_id"], actor["binding_status"]), ("person_01", "missing_entity"))
        self.assertEqual(self.bind().status_code, 404)
        self.assertEqual(self.unbind().status_code, 200)
        self.assertTrue(self.runtime.engine.verify_replay()["ok"])

    def test_concurrent_claims_only_bind_one_actor(self):
        with TestClient(self.runtime.app) as client:
            def claim(source):
                return client.put(f"/api/actors/{source}/alice/entity", json=self.payload,
                                  headers=self.headers).status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                statuses = list(pool.map(claim, ["tiktok", "youtube"]))
        self.assertEqual(sorted(statuses), [200, 409])
        self.assertEqual(len(self.runtime.bindings.history()), 1)

    def test_health_exposes_binding_capability_without_secret(self):
        health = self.client.get("/api/health").json()
        self.assertEqual((health["mvp"], health["version"]), ("009", "0.10.0"))
        self.assertTrue(health["operator_binding_enabled"])
        self.assertEqual(health["actor_bindings_total"], 0)
        self.bind()
        self.assertEqual(self.client.get("/api/health").json()["actor_bindings_total"], 1)
        self.assertNotIn("test-operator-token", self.client.get("/api/health").text)


if __name__ == "__main__":
    unittest.main()
