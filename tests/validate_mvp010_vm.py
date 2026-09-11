#!/usr/bin/env python3
"""Read-only validation for the MVP-010 management page and API."""
import argparse
import json
import urllib.error
import urllib.request


def get_json(base, path, headers=None):
    request = urllib.request.Request(base.rstrip("/") + path, headers=headers or {})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def validate(base):
    health = get_json(base, "/api/health")
    assert (health["mvp"], health["version"]) == ("010", "0.11.0"), health
    assert health["integration_management_enabled"] and health["replay_ok"], health
    assert get_json(base, "/api/replay/verify")["ok"]
    with urllib.request.urlopen(base.rstrip("/") + "/manage/", timeout=15) as response:
        page = response.read().decode("utf-8")
    assert response.status == 200 and "Live Infinita" in page and "Gerência" in page
    try:
        get_json(base, "/api/manage/integrations")
        raise AssertionError("management status allowed without operator key")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, f"expected 401, got {exc.code}"
    print(f"MVP-010 PASS: page, auth, health and replay; configured={health['integrations']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    validate(parser.parse_args().base_url)
