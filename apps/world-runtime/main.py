from __future__ import annotations

import asyncio
import json
import os
import secrets
import sys
import time
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from engine import DeterministicWorldEngine

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILE = ROOT / "examples" / "world-state.mvp001.bootstrap.json"
RENDERER_DIR = ROOT / "apps" / "renderer-web"
DATA_DIR = Path(os.environ.get("LIVE_INFINITA_DATA_DIR", "/var/lib/live-infinita"))
AUDIENCE_EVENTS_FILE = DATA_DIR / "audience-events.jsonl"
AUDIENCE_PROPOSALS_FILE = DATA_DIR / "audience-proposals.jsonl"
ACTOR_OBSERVATIONS_FILE = DATA_DIR / "actor-observations.jsonl"
ACTOR_BINDINGS_FILE = DATA_DIR / "actor-bindings.jsonl"
OPERATOR_TOKEN = os.environ.get("LIVE_INFINITA_OPERATOR_TOKEN", "")
GATEWAY_DIR = ROOT / "apps" / "gateway"
AUDIENCE_DIR = ROOT / "apps" / "audience"
ACTORS_DIR = ROOT / "apps" / "actors"
for path in (GATEWAY_DIR, AUDIENCE_DIR, ACTORS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from pipeline import GatewayPipeline  # noqa: E402
from aggregator import AudienceAggregator  # noqa: E402
from store import ActorStore  # noqa: E402
from bindings import ActorBindingStore, BindingConflict  # noqa: E402

app = FastAPI(title="Live Infinita MVP-009", version="0.10.0")
clients: set[WebSocket] = set()
world_lock = asyncio.Lock()
audience_lock = asyncio.Lock()
actor_lock = asyncio.Lock()
engine = DeterministicWorldEngine(BOOTSTRAP_FILE, DATA_DIR)
pipeline = GatewayPipeline()
aggregator = AudienceAggregator()
actors = ActorStore(ACTOR_OBSERVATIONS_FILE)
bindings = ActorBindingStore(ACTOR_BINDINGS_FILE)


def require_operator(authorization: str | None = Header(default=None)) -> None:
    if not OPERATOR_TOKEN:
        raise HTTPException(status_code=503, detail="chave do operador não configurada")
    expected = f"Bearer {OPERATOR_TOKEN}".encode("utf-8")
    if not secrets.compare_digest((authorization or "").encode("utf-8"), expected):
        raise HTTPException(status_code=401, detail="chave do operador inválida",
                            headers={"WWW-Authenticate": "Bearer"})


class ActorEntityRequest(BaseModel):
    entity_id: str = Field(min_length=1, max_length=200, pattern=r"^\S+$")


def actor_views() -> list[dict[str, Any]]:
    links = bindings.current()
    characters = {entity["id"] for entity in engine.load_world().get("entities", [])
                  if entity.get("type") == "human"}
    result = actors.actors()
    for actor in result:
        entity_id = links.get(actor["actor_key"])
        actor["entity_id"] = entity_id
        actor["binding_status"] = ("unbound" if entity_id is None else
                                   "active" if entity_id in characters else "missing_entity")
    return result


class SimulationRequest(BaseModel):
    action: str


class GatewayEventRequest(BaseModel):
    source: str = "simulator"
    source_event_id: str = "local-1"
    actor_id: str = "local-user"
    display_name: str | None = None
    kind: str = "text"
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SourceEventRequest(BaseModel):
    source_event_id: str
    actor_id: str
    display_name: str | None = None
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class AudienceEventRequest(BaseModel):
    source_event_id: str
    actor_id: str
    display_name: str | None = None
    kind: str
    metadata: dict[str, Any] = Field(default_factory=dict)


async def broadcast(message: dict) -> None:
    dead: list[WebSocket] = []
    for client in list(clients):
        try:
            await client.send_json(message)
        except Exception:
            dead.append(client)
    for client in dead:
        clients.discard(client)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    result: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                result.append(json.loads(line))
    return result


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def current_proposals() -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for record in read_jsonl(AUDIENCE_PROPOSALS_FILE):
        proposal_id = str(record.get("proposal_id", "")).strip()
        if not proposal_id:
            continue
        if proposal_id not in latest:
            order.append(proposal_id)
        latest[proposal_id] = record
    return [latest[proposal_id] for proposal_id in order]


def backfill_actor_store() -> None:
    """Recover actor observations from historical audience/world logs once, idempotently."""
    for row in read_jsonl(AUDIENCE_EVENTS_FILE):
        actor = row.get("actor") or {}
        actors.observe(
            source=str(row.get("source") or "unknown"),
            actor_id=str(actor.get("actor_id") or ""),
            display_name=actor.get("display_name"),
            kind=str(row.get("kind") or "unknown"),
            source_event_id=str(row.get("source_event_id") or ""),
            metadata={"backfill": True, **dict(row.get("metadata") or {})},
            observed_at_unix=row.get("received_at_unix"),
        )

    for row in engine.read_jsonl(engine.events_file):
        context = row.get("context") or {}
        source_event_id = str(context.get("source_event_id") or "")
        actor_id = str(context.get("actor_id") or "")
        if not source_event_id or not actor_id:
            continue
        actors.observe(
            source=str(row.get("source") or "unknown"),
            actor_id=actor_id,
            display_name=context.get("display_name"),
            kind=str(context.get("kind") or "text"),
            source_event_id=source_event_id,
            metadata={
                "backfill": True,
                "world_event_id": row.get("event_id"),
                "timestamp_basis": "event" if context.get("observed_at_unix") is not None else "backfill",
            },
            observed_at_unix=context.get("observed_at_unix"),
        )


backfill_actor_store()


async def observe_actor(
    *,
    source: str,
    actor_id: str,
    display_name: str | None,
    kind: str,
    source_event_id: str,
    metadata: dict[str, Any],
    observed_at_unix: float | None = None,
) -> bool:
    async with actor_lock:
        return actors.observe(
            source=source,
            actor_id=actor_id,
            display_name=display_name,
            kind=kind,
            source_event_id=source_event_id,
            metadata=metadata,
            observed_at_unix=observed_at_unix,
        )


async def process_gateway_payload(payload: dict[str, Any]) -> JSONResponse:
    try:
        normalized, proposed, validation = pipeline.process(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    observed_at_unix = time.time()
    await observe_actor(
        source=normalized.source,
        actor_id=normalized.actor.actor_id,
        display_name=normalized.actor.display_name,
        kind=normalized.kind,
        source_event_id=normalized.source_event_id,
        metadata={"channel": "gateway", **dict(normalized.metadata)},
        observed_at_unix=observed_at_unix,
    )

    normalized_dict = normalized.to_dict()
    envelope = {
        "normalized_event": normalized_dict,
        "proposed_action": {"action": proposed.action, "confidence": proposed.confidence, "reason": proposed.reason},
        "validation": {"accepted": validation.accepted, "action": validation.action, "reason": validation.reason},
    }
    if not validation.accepted or validation.action is None:
        return JSONResponse({"ok": False, **envelope}, status_code=422)

    async with world_lock:
        try:
            event, delta, world = engine.commit_action(
                validation.action,
                source=normalized.source,
                context={
                    "envelope_version": normalized.envelope_version,
                    "source_event_id": normalized.source_event_id,
                    "actor_id": normalized.actor.actor_id,
                    "display_name": normalized.actor.display_name,
                    "kind": normalized.kind,
                    "observed_at_unix": observed_at_unix,
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
        "mvp": "009",
        "version": "0.10.0",
        "replay_ok": verification["ok"],
        "state_hash": verification["current_hash"],
        "pipeline": ["real-source-bridge", "actor-state", "audience-side-channel", "audience-aggregator", "proposal-gate", "intent", "validator", "runtime"],
        "audience_events": ["join", "like", "gift"],
        "audience_events_total": len(read_jsonl(AUDIENCE_EVENTS_FILE)),
        "audience_proposals_total": len(current_proposals()),
        "audience_proposal_log_records": len(read_jsonl(AUDIENCE_PROPOSALS_FILE)),
        "audience_rules": aggregator.rules_snapshot(),
        "actor_observations_total": len(actors.observations()),
        "actors_total": len(actors.actors()),
        "actor_bindings_total": len(bindings.current()),
        "operator_binding_enabled": bool(OPERATOR_TOKEN),
        "identity_namespace": "source:actor_id",
        "cross_platform_auto_merge": False,
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


@app.get("/api/actors")
async def get_actors() -> JSONResponse:
    return JSONResponse({"actors": actor_views(), "observations_total": len(actors.observations())})


@app.get("/api/actors/{source}/{actor_id}")
async def get_actor(source: str, actor_id: str) -> JSONResponse:
    key = f"{source.strip().lower()}:{actor_id.strip()}"
    actor = next((item for item in actor_views() if item["actor_key"] == key), None)
    if actor is None:
        raise HTTPException(status_code=404, detail="ator não encontrado")
    return JSONResponse(actor)


@app.get("/api/actors/{source}/{actor_id}/bindings")
async def get_actor_bindings(source: str, actor_id: str) -> JSONResponse:
    actor = actors.get(source, actor_id)
    if actor is None:
        raise HTTPException(status_code=404, detail="ator não encontrado")
    return JSONResponse({"history": [row for row in bindings.history()
                                     if row["actor_key"] == actor["actor_key"]]})


@app.put("/api/actors/{source}/{actor_id}/entity", dependencies=[Depends(require_operator)])
async def bind_actor_entity(source: str, actor_id: str, request: ActorEntityRequest) -> JSONResponse:
    async with world_lock, actor_lock:
        actor = actors.get(source, actor_id)
        if actor is None:
            raise HTTPException(status_code=404, detail="ator não encontrado")
        entity = next((item for item in engine.load_world().get("entities", [])
                       if item["id"] == request.entity_id), None)
        if entity is None:
            raise HTTPException(status_code=404, detail="personagem não encontrado")
        if entity.get("type") != "human":
            raise HTTPException(status_code=422, detail="entidade precisa ser um personagem humano")
        try:
            changed = bindings.bind(actor["actor_key"], request.entity_id)
        except BindingConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "changed": changed, "world_mutated": False,
                         "actor_key": actor["actor_key"], "entity_id": request.entity_id})


@app.delete("/api/actors/{source}/{actor_id}/entity", dependencies=[Depends(require_operator)])
async def unbind_actor_entity(source: str, actor_id: str, request: ActorEntityRequest) -> JSONResponse:
    async with actor_lock:
        actor = actors.get(source, actor_id)
        if actor is None:
            raise HTTPException(status_code=404, detail="ator não encontrado")
        try:
            changed = bindings.unbind(actor["actor_key"], request.entity_id)
        except BindingConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse({"ok": True, "changed": changed, "world_mutated": False,
                         "actor_key": actor["actor_key"], "entity_id": None})


@app.get("/api/audience/events")
async def get_audience_events() -> JSONResponse:
    return JSONResponse({"events": read_jsonl(AUDIENCE_EVENTS_FILE)})


@app.get("/api/audience/rules")
async def get_audience_rules() -> JSONResponse:
    return JSONResponse({"rules": aggregator.rules_snapshot()})


@app.get("/api/audience/proposals")
async def get_audience_proposals() -> JSONResponse:
    return JSONResponse({"proposals": current_proposals(), "log_records": len(read_jsonl(AUDIENCE_PROPOSALS_FILE))})


@app.post("/api/audience/proposals/{proposal_id}/commit")
async def commit_audience_proposal(proposal_id: str) -> JSONResponse:
    proposal = next((p for p in current_proposals() if p.get("proposal_id") == proposal_id), None)
    if proposal is None:
        raise HTTPException(status_code=404, detail="proposta não encontrada")
    if proposal.get("status") != "pending":
        raise HTTPException(status_code=409, detail="proposta não está pendente")

    response = await process_gateway_payload({
        "source": "api",
        "source_event_id": f"audience-proposal-{proposal_id}",
        "actor_id": "audience-aggregator",
        "display_name": "Audience Aggregator",
        "kind": "text",
        "text": proposal["gateway_text"],
        "metadata": {"proposal_id": proposal_id, "rule_id": proposal["rule_id"]},
    })
    if response.status_code < 300:
        append_jsonl(AUDIENCE_PROPOSALS_FILE, {**proposal, "status": "committed", "committed_at_unix": time.time()})
    return response


@app.get("/api/replay/verify")
async def verify_replay() -> JSONResponse:
    result = engine.verify_replay()
    return JSONResponse(result, status_code=200 if result["ok"] else 409)


@app.post("/api/gateway/event")
async def gateway_event(request: GatewayEventRequest) -> JSONResponse:
    return await process_gateway_payload(request.model_dump())


@app.post("/api/source/{source}/event")
async def source_event(source: str, request: SourceEventRequest) -> JSONResponse:
    payload = request.model_dump()
    payload["source"] = source
    payload["kind"] = "text"
    return await process_gateway_payload(payload)


@app.post("/api/audience/{source}/event")
async def audience_event(source: str, request: AudienceEventRequest) -> JSONResponse:
    source = source.strip().lower()
    if source not in {"tiktok", "youtube", "simulator", "api"}:
        raise HTTPException(status_code=400, detail=f"fonte de audiência não permitida: {source}")
    kind = request.kind.strip().lower()
    if kind not in {"join", "like", "gift"}:
        raise HTTPException(status_code=400, detail=f"evento de audiência não permitido: {kind}")

    record = {
        "envelope_version": "1.0",
        "source": source,
        "source_event_id": request.source_event_id,
        "actor": {"actor_id": request.actor_id, "display_name": request.display_name},
        "kind": kind,
        "metadata": request.metadata,
        "received_at_unix": time.time(),
    }

    async with audience_lock:
        existing = read_jsonl(AUDIENCE_EVENTS_FILE)
        duplicate = any(item.get("source") == source and item.get("source_event_id") == request.source_event_id for item in existing)
        proposals: list[dict[str, Any]] = []
        if not duplicate:
            append_jsonl(AUDIENCE_EVENTS_FILE, record)
            proposals = aggregator.ingest(record, now=record["received_at_unix"])
            for proposal in proposals:
                append_jsonl(AUDIENCE_PROPOSALS_FILE, proposal)

    if not duplicate:
        await observe_actor(
            source=source,
            actor_id=request.actor_id,
            display_name=request.display_name,
            kind=kind,
            source_event_id=request.source_event_id,
            metadata={"channel": "audience", **dict(request.metadata)},
            observed_at_unix=record["received_at_unix"],
        )
        await broadcast({"type": "audience_event", "event": record})
        for proposal in proposals:
            await broadcast({"type": "audience_proposal", "proposal": proposal})

    return JSONResponse({
        "ok": True,
        "duplicate": duplicate,
        "world_mutated": False,
        "event": record,
        "proposals": proposals,
    }, status_code=200 if duplicate else 202)


@app.post("/api/simulate")
async def simulate(request: SimulationRequest) -> JSONResponse:
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
        "source_event_id": f"preview-{engine.load_world().get('sequence', 0) + 1}",
        "actor_id": "preview-user",
        "display_name": "Preview User",
        "kind": "text",
        "text": text,
        "metadata": {"legacy_action": request.action},
    })


@app.post("/api/world/reset")
async def reset_world() -> JSONResponse:
    return await process_gateway_payload({
        "source": "api",
        "source_event_id": f"reset-{engine.load_world().get('sequence', 0) + 1}",
        "actor_id": "system",
        "display_name": "System",
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
