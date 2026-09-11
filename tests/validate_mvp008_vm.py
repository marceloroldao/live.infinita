#!/usr/bin/env python3
"""Read-only by default; --write creates three isolated actor observations."""
import argparse
import json
import urllib.error
import urllib.request
import uuid


def validate(base, write=False):
    def request(path, payload=None, expected=200):
        data = None if payload is None else json.dumps(payload).encode()
        req = urllib.request.Request(base.rstrip("/") + path, data=data,
                                     headers={"Content-Type": "application/json"})
        try:
            response = urllib.request.urlopen(req, timeout=15)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            body = json.load(response)
            if response.code != expected:
                raise RuntimeError(f"{path}: HTTP {response.code}, expected {expected}: {body}")
            return body

    health = request("/api/health")
    assert (health["mvp"], health["version"]) in {("008", "0.9.0"), ("009", "0.10.0")}, health
    assert health["replay_ok"] and health["cross_platform_auto_merge"] is False
    assert "audience_rules" in health and "audience_proposal_log_records" in health
    assert request("/api/replay/verify")["ok"]
    actors = request("/api/actors")
    print(f"Actor State health/replay OK; MVP={health['mvp']}; actors={len(actors['actors'])}; observations={actors['observations_total']}")
    if not write:
        return

    actor_id = "mvp008-check-" + uuid.uuid4().hex
    before = request("/api/world")
    event = {"source_event_id": actor_id + "-join", "actor_id": actor_id,
             "display_name": "MVP008 Check", "kind": "join"}
    for source in ("tiktok", "youtube"):
        result = request(f"/api/audience/{source}/event", event, 202)
        assert result["world_mutated"] is False
    assert request("/api/audience/tiktok/event", event)["duplicate"]
    request("/api/source/tiktok/event", {
        "source_event_id": actor_id + "-comment", "actor_id": actor_id,
        "display_name": "MVP008 Renamed", "text": "hello everyone",
    }, 422)
    tt = request(f"/api/actors/tiktok/{actor_id}")
    yt = request(f"/api/actors/youtube/{actor_id}")
    assert tt["interactions_by_kind"] == {"join": 1, "text": 1}, tt
    assert tt["display_name"] == "MVP008 Renamed", tt
    assert yt["interactions_total"] == 1, yt
    assert tt["actor_key"] != yt["actor_key"]
    assert request("/api/world") == before, "World changed during validation; repeat without concurrent producers"
    assert request("/api/replay/verify")["ok"]
    print(f"PASS: identity, duplicate, rename, namespaces and unchanged world; actor_id={actor_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    validate(args.base_url, args.write)
