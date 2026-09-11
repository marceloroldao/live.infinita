from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import DeterministicWorldEngine

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILE = ROOT / "examples" / "world-state.mvp001.bootstrap.json"
RENDERER_DIR = ROOT / "apps" / "renderer-web"
DATA_DIR = Path(os.environ.get("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))

app = FastAPI(title="Live Infinita MVP-002", version="0.3.0")
clients: set[WebSocket] = set()
world_lock = asyncio.Lock()
engine = DeterministicWorldEngine(BOOTSTRAP_FILE, DATA_DIR)


class SimulationRequest(BaseModel):
    action: str


async def broadcast(message: dict) -> None:
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
    verification = engine.verify_replay()
    return JSONResponse({
        "ok": True,
        "service": "live-infinita",
        "mvp": "002",
        "version": "0.3.0",
        "replay_ok": verification["ok"],
        "state_hash": verification["current_hash"],
    })


@app.get("/api/world")
async def get_world() -> JSONResponse:
    return JSONResponse(engine.load_world())


@app.get("/api/events")
async def get_events() -> JSONResponse:
    return JSONResponse({"events": engine.read_jsonl(engine.events_file)})


@app.get("/api/deltas")
async def get_deltas() -> JSONResponse:
    return JSONResponse({"deltas": engine.read_jsonl(engine.deltas_file)})


@app.get("/api/replay/verify")
async def verify_replay() -> JSONResponse:
    result = engine.verify_replay()
    return JSONResponse(result, status_code=200 if result["ok"] else 409)


@app.post("/api/simulate")
async def simulate(request: SimulationRequest) -> JSONResponse:
    async with world_lock:
        try:
            event, delta, world = engine.commit_action(request.action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    await broadcast({"type": "world_state", "world": world, "event": event, "delta": delta})
    return JSONResponse({"ok": True, "event": event, "delta": delta, "world": world})


@app.post("/api/world/reset")
async def reset_world() -> JSONResponse:
    async with world_lock:
        event, delta, world = engine.commit_action("reset")
    await broadcast({"type": "world_state", "world": world, "event": event, "delta": delta})
    return JSONResponse({"ok": True, "event": event, "delta": delta, "world": world})


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    clients.add(websocket)
    await websocket.send_json({"type": "world_state", "world": engine.load_world()})
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
