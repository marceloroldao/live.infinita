from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parents[2]
WORLD_FILE = ROOT / "examples" / "world-state.mvp001.json"
RENDERER_DIR = ROOT / "apps" / "renderer-web"

app = FastAPI(title="Live Infinita MVP-001", version="0.1.0")
clients: set[WebSocket] = set()
world_lock = asyncio.Lock()


def load_world() -> dict[str, Any]:
    with WORLD_FILE.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def save_world(world: dict[str, Any]) -> None:
    tmp = WORLD_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(world, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(WORLD_FILE)


async def broadcast(message: dict[str, Any]) -> None:
    dead: list[WebSocket] = []
    for client in list(clients):
        try:
            await client.send_json(message)
        except Exception:
            dead.append(client)
    for client in dead:
        clients.discard(client)


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"ok": True, "service": "live-infinita", "mvp": "001"})


@app.get("/api/world")
async def get_world() -> JSONResponse:
    return JSONResponse(load_world())


@app.post("/api/world/reset")
async def reset_world() -> JSONResponse:
    async with world_lock:
        world = load_world()
        world["version"] = int(world.get("version", 0)) + 1
        save_world(world)
    await broadcast({"type": "world_state", "world": world})
    return JSONResponse(world)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    await websocket.send_json({"type": "world_state", "world": load_world()})
    try:
        while True:
            message = await websocket.receive_json()
            if message.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        clients.discard(websocket)
    except Exception:
        clients.discard(websocket)
        await websocket.close()


app.mount("/", StaticFiles(directory=str(RENDERER_DIR), html=True), name="renderer")
