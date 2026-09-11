from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, LiveEndEvent


@dataclass(frozen=True)
class BridgeConfig:
    unique_id: str
    gateway_url: str
    timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        unique_id = os.environ.get("TIKTOK_UNIQUE_ID", "").strip()
        if not unique_id:
            raise RuntimeError("TIKTOK_UNIQUE_ID não configurado")
        if not unique_id.startswith("@"):
            unique_id = "@" + unique_id
        gateway_url = os.environ.get(
            "LIVE_INFINITA_TIKTOK_GATEWAY_URL",
            "http://127.0.0.1:8080/api/source/tiktok/event",
        ).strip()
        timeout = float(os.environ.get("LIVE_INFINITA_SOURCE_TIMEOUT", "5"))
        return cls(unique_id=unique_id, gateway_url=gateway_url, timeout_seconds=timeout)


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def comment_to_payload(event: Any, room_id: Any = None) -> dict[str, Any]:
    user = getattr(event, "user", None)
    actor_id = (
        getattr(user, "unique_id", None)
        or getattr(user, "id", None)
        or getattr(user, "user_id", None)
        or "unknown"
    )
    display_name = (
        getattr(user, "nickname", None)
        or getattr(user, "unique_id", None)
        or str(actor_id)
    )
    comment = str(getattr(event, "comment", "")).strip()
    common = getattr(event, "common", None)
    source_event_id = (
        getattr(common, "msg_id", None)
        or getattr(common, "message_id", None)
        or f"comment-{time.time_ns()}"
    )
    return {
        "source_event_id": str(source_event_id),
        "actor_id": str(actor_id),
        "display_name": str(display_name),
        "text": comment,
        "metadata": {
            "event_type": "comment",
            "room_id": _scalar(room_id),
            "bridge": "TikTokLive",
        },
    }


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"raw": raw}
        return exc.code, data


def build_client(config: BridgeConfig) -> TikTokLiveClient:
    client = TikTokLiveClient(unique_id=config.unique_id)

    @client.on(ConnectEvent)
    async def on_connect(event: ConnectEvent) -> None:
        print(
            f"[tiktok] conectado a {config.unique_id} room_id={client.room_id}",
            flush=True,
        )

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent) -> None:
        payload = comment_to_payload(event, room_id=client.room_id)
        if not payload["text"]:
            return
        status, result = post_json(config.gateway_url, payload, config.timeout_seconds)
        accepted = bool(result.get("ok")) if isinstance(result, dict) else False
        print(
            f"[tiktok] comentário actor={payload['display_name']!r} "
            f"text={payload['text']!r} http={status} accepted={accepted}",
            flush=True,
        )

    @client.on(DisconnectEvent)
    async def on_disconnect(_: DisconnectEvent) -> None:
        print("[tiktok] desconectado", flush=True)

    @client.on(LiveEndEvent)
    async def on_live_end(_: LiveEndEvent) -> None:
        print("[tiktok] live encerrada", flush=True)

    return client


def main() -> int:
    try:
        config = BridgeConfig.from_env()
    except Exception as exc:
        print(f"[tiktok] configuração inválida: {exc}", file=sys.stderr, flush=True)
        return 2

    print(
        f"[tiktok] iniciando bridge {config.unique_id} -> {config.gateway_url}",
        flush=True,
    )
    client = build_client(config)
    client.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
