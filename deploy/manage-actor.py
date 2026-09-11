#!/usr/bin/env python3
"""Operator helper: list actors/characters, bind or unbind without printing tokens."""
import argparse
import json
import os
from pathlib import Path
import urllib.error
import urllib.request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["actors", "characters", "bind", "unbind"])
    parser.add_argument("source", nargs="?")
    parser.add_argument("actor_id", nargs="?")
    parser.add_argument("entity_id", nargs="?")
    args = parser.parse_args()
    headers = {}
    data = None
    method = "GET"
    if args.action in {"actors", "characters"}:
        path = "/api/actors" if args.action == "actors" else "/api/world"
    else:
        if not all((args.source, args.actor_id, args.entity_id)):
            parser.error("informe source actor_id entity_id")
        token = os.environ.get("LIVE_INFINITA_OPERATOR_TOKEN", "")
        if not token:
            try:
                lines = Path("/etc/live-infinita/operator.env").read_text().splitlines()
                token = next(line.split("=", 1)[1] for line in lines
                             if line.startswith("LIVE_INFINITA_OPERATOR_TOKEN="))
            except (OSError, StopIteration):
                parser.error("execute com sudo para ler a chave local do operador")
        from urllib.parse import quote
        path = f"/api/actors/{quote(args.source, safe='')}/{quote(args.actor_id, safe='')}/entity"
        method = "PUT" if args.action == "bind" else "DELETE"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        data = json.dumps({"entity_id": args.entity_id}).encode()
    req = urllib.request.Request("http://127.0.0.1:8080" + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode()}")
        return 1
    if args.action == "characters":
        result = [e for e in result["entities"] if e.get("type") == "human"]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
