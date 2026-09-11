#!/usr/bin/env python3
"""Validação externa e somente leitura do MVP-011."""
import json
import sys
import urllib.error
import urllib.request


def read(url: str) -> tuple[int, bytes]:
    with urllib.request.urlopen(url, timeout=15) as response:
        return response.status, response.read()


def main(base: str) -> None:
    base = base.rstrip("/")
    _, raw = read(base + "/api/health")
    health = json.loads(raw)
    assert (health["mvp"], health["version"]) == ("011", "0.12.0"), health
    assert health["replay_ok"], health
    assert b"login-form" in read(base + "/")[1]
    assert b"/gdscript/app.js" in read(base + "/gdscript/")[1]
    assert read(base + "/godot/")[0] == 200
    try:
        read(base + "/api/manage/integrations")
        raise AssertionError("API de gerência aceitou acesso sem login")
    except urllib.error.HTTPError as exc:
        assert exc.code == 401, exc.code
    print("MVP-011 PASS: login, manager, Godot, GDScript e replay OK.")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "https://live.etbra.com.br")
