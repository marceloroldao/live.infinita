#!/usr/bin/env python3
"""Validação externa e somente leitura do MVP-012."""
import json
import sys
import urllib.error
import urllib.request


def read(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.status, response.read()


def main(base: str) -> None:
    base = base.rstrip("/")
    health = json.loads(read(base + "/api/health")[1])
    assert (health["mvp"], health["version"]) == ("012", "0.13.0"), health
    assert health["replay_ok"], health
    page = read(base + "/")[1]
    assert b'id="overview"' in page and b"monitoring.css" in page
    assert read(base + "/monitoring.css")[0] == 200
    for path in ("/godot/", "/gdscript/"):
        assert read(base + path)[0] == 200
    try:
        read(base + "/api/manage/monitor")
        raise AssertionError("Monitor aceitou acesso sem login")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, exc.code
    print("MVP-012 PASS: monitor, proteção, Godot, GDScript e replay OK.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://live.etbra.com.br")
