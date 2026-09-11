from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
WORLD_FILE = ROOT / "examples" / "world-state.mvp001.json"
BOOTSTRAP_FILE = ROOT / "examples" / "world-state.mvp001.bootstrap.json"
RENDERER_DIR = ROOT / "apps" / "renderer-web"

app = FastAPI(title="Live Infinita MVP-001", version="0.2.0")
clients: set[WebSocket] = set()
world_lock = asyncio.Lock()


class SimulationRequest(BaseModel):
    action: str


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_world() -> dict[str, Any]:
    return load_json(WORLD_FILE)


def save_world(world: dict[str, Any]) -> None:
    tmp = WORLD_FILE.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(world, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    tmp.replace(WORLD_FILE)


def find_entity(world: dict[str, Any], entity_id: str) -> dict[str, Any] | None:
    for entity in world.get("entities", []):
        if entity.get("id") == entity_id:
            return entity
    return None


def apply_simulation(world: dict[str, Any], action: str) -> tuple[dict[str, Any], str]:
    action = action.strip().lower()
    narration = ""

    if action == "spawn_person":
        person = find_entity(world, "person_01")
        if person is None:
            world.setdefault("entities", []).append(
                {
                    "id": "person_01",
                    "type": "human",
                    "position": {"x": 650, "y": 320},
                    "scale": 1.0,
                    "properties": {"label": "Visitante"},
                }
            )
            narration = "Um visitante entra silenciosamente na clareira."
        else:
            narration = "O visitante já está na clareira."

    elif action == "move_tree":
        tree = find_entity(world, "tree_01")
        if tree is None:
            raise ValueError("tree_01 não existe")
        x = int(tree.setdefault("position", {}).get("x", 220))
        tree["position"]["x"] = 360 if x < 300 else 220
        narration = "A árvore muda de posição no estado do mundo."

    elif action == "toggle_fire":
        fire = find_entity(world, "fire_01")
        if fire is None:
            raise ValueError("fire_01 não existe")
        properties = fire.setdefault("properties", {})
        properties["lit"] = not bool(properties.get("lit", True))
        narration = "A fogueira se acende." if properties["lit"] else "A fogueira se apaga."

    elif action == "set_night":
        environment = world.setdefault("environment", {})
        environment["period"] = "night"
        narration = "A noite cai sobre a clareira."

    elif action == "set_day":
        environment = world.setdefault("environment", {})
        environment["period"] = "day"
        narration = "A luz do dia retorna à clareira."

    elif action == "reset":
        current_version = int(world.get("version", 0))
        world = copy.deepcopy(load_json(BOOTSTRAP_FILE))
        world["version"] = current_version
        narration = "O mundo retorna ao estado inicial do MVP-001."

    else:
        raise ValueError(f"ação desconhecida: {action}")

    world["version"] = int(world.get("version", 0)) + 1
    world.setdefault("narration", {})["text"] = narration
    world["last_event"] = {
        "type": "simulator_action",
        "action": action,
        "source": "mvp001-simulator",
    }
    world.setdefault("provenance", {})["last_source"] = "simulator"
    return world, narration


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
    return JSONResponse({"ok": True, "service": "live-infinita", "mvp": "001", "version": "0.2.0"})


@app.get("/api/world")
async def get_world() -> JSONResponse:
    return JSONResponse(load_world())


@app.post("/api/simulate")
async def simulate(request: SimulationRequest) -> JSONResponse:
    async with world_lock:
        world = load_world()
        try:
            world, _ = apply_simulation(world, request.action)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_world(world)
    await broadcast({"type": "world_state", "world": world})
    return JSONResponse({"ok": True, "action": request.action, "world": world})


@app.post("/api/world/reset")
async def reset_world() -> JSONResponse:
    async with world_lock:
        world = load_world()
        world, _ = apply_simulation(world, "reset")
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
