from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from engine import DeterministicWorldEngine

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILE = ROOT / "examples" / "world-state.mvp001.bootstrap.json"
RENDERER_DIR = ROOT / "apps" / "renderer-web"
DATA_DIR = Path(os.environ.get("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))
GATEWAY_DIR = ROOT / "apps" / "gateway"
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

from pipeline import GatewayPipeline  # noqa: E402

app = FastAPI(title="Live Infinita MVP-003", version="0.4.0")
clients: set[WebSocket] = set()
world_lock = asyncio.Lock()
engine = DeterministicWorldEngine(BOOTSTRAP_FILE, DATA_DIR)
pipeline = GatewayPipeline()


class SimulationRequest(BaseModel):
    action: str


class GatewayEventRequest(BaseModel):
    source: str = "simulator"
    actor_id: str = "local-user"
    kind: str = "text"
    text: str
    metadata: dict[str, Any] = {}


async def broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    for client in list(clients):
        try:
            await client.send_json(message)
        except Exception:
            dead.append(client)
    for client in dead:
        clients.discard(client)


async def process_gateway_payload(payload: dict[str, Any]) -> JSONResponse:
    try:
        normalized, proposed, validation = pipeline.process(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    envelope = {
        "normalized_event": {
            "source": normalized.source,
            "actor_id": normalized.actor_id,
            "kind": normalized.kind,
            "text": normalized.text,
            "metadata": normalized.metadata,
        },
        "proposed_action": {
            "action": proposed.action,
            "confidence": proposed.confidence,
            "reason": proposed.reason,
        },
        "validation": {
            "accepted": validation.accepted,
            "action": validation.action,
            "reason": validation.reason,
        },
    }

    if not validation.accepted or validation.action is None:
        return JSONResponse({"ok": False, **envelope}, status_code=422)

    async with world_lock:
        try:
            event, delta, world = engine.commit_action(
                validation.action,
                source=normalized.source,
                context={
                    "actor_id": normalized.actor_id,
                    "kind": normalized.kind,
                    "text": normalized.text,
                    "metadata": normalized.metadata,
                    "intent_reason": proposed.reason,
                    "validation_reason": validation.reason,
                },
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    await broadcast({"type": "world_state", "world": world, "event": event, "delta": delta, "gateway": envelope})
    return JSONResponse({"ok": True, **envelope, "event": event, "delta": delta, "world": world})


@app.get("/api/health")
async def health() -> JSONResponse:
    verification = engine.verify_replay()
    return JSONResponse({
        "ok": True,
        "service": "live-infinita",
        "mvp": "003",
        "version": "0.4.0",
        "replay_ok": verification["ok"],
        "state_hash": verification["current_hash"],
        "pipeline": ["gateway", "intent", "validator", "runtime"],
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


@app.post("/api/gateway/event")
async def gateway_event(request: GatewayEventRequest) -> JSONResponse:
    return await process_gateway_payload(request.model_dump())


@app.post("/api/simulate")
async def simulate(request: SimulationRequest) -> JSONResponse:
    # Compatibilidade com o MVP-001/002: o botão antigo agora entra pelo Gateway.
    text_by_action = {
        "spawn_person": "+ visitante",
        "move_tree": "mover árvore",
        "toggle_fire": "fogueira",
        "set_night": "noite",
        "set_day": "dia",
        "reset": "reset",
    }
    text = text_by_action.get(request.action)
    if text is None:
        raise HTTPException(status_code=400, detail=f"ação desconhecida: {request.action}")
    return await process_gateway_payload({
        "source": "simulator",
        "actor_id": "preview-user",
        "kind": "text",
        "text": text,
        "metadata": {"legacy_action": request.action},
    })


@app.post("/api/world/reset")
async def reset_world() -> JSONResponse:
    return await process_gateway_payload({
        "source": "api",
        "actor_id": "system",
        "kind": "text",
        "text": "reset",
        "metadata": {},
    })


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
