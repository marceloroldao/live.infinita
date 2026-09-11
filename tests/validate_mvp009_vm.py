#!/usr/bin/env python3
"""Read-only production check for MVP-009; no test actors or world actions."""
import argparse
import json
import urllib.error
import urllib.request


def validate(base):
    def get(path):
        with urllib.request.urlopen(base.rstrip("/") + path, timeout=15) as r:
            return json.load(r)
    health = get("/api/health")
    assert (health["mvp"], health["version"]) == ("009", "0.10.0"), health
    assert health["operator_binding_enabled"], "operator key not configured"
    assert health["replay_ok"] and get("/api/replay/verify")["ok"]
    actors = get("/api/actors")
    for actor in actors["actors"]:
        assert actor["binding_status"] in {"unbound", "active", "missing_entity"}
    # An unauthenticated request must not be able to change a binding.
    req = urllib.request.Request(base.rstrip("/") + "/api/actors/api/mvp009-check/entity",
                                 data=b'{"entity_id":"person_01"}',
                                 headers={"Content-Type": "application/json"}, method="PUT")
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            raise AssertionError(f"unauthenticated binding returned HTTP {r.status}")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, f"expected 401, got {exc.code}"
    print(f"MVP-009 PASS: health, replay, operator protection; "
          f"actors={len(actors['actors'])}; bindings={health['actor_bindings_total']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    validate(parser.parse_args().base_url)
