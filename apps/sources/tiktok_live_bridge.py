from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from TikTokLive import TikTokLiveClient
from TikTokLive.events import CommentEvent, ConnectEvent, DisconnectEvent, GiftEvent, JoinEvent, LikeEvent, LiveEndEvent

from tiktok_audience_mapping import gift_to_payload, join_to_payload, like_to_payload
from tiktok_mapping import comment_to_payload


@dataclass(frozen=True)
class BridgeConfig:
    unique_id: str
    gateway_url: str
    audience_url: str
    timeout_seconds: float = 5.0
    retry_seconds: float = 30.0
    sign_api_key: str | None = None
    status_file: Path = Path("/var/lib/live-infinita/tiktok-status.json")

    @classmethod
    def from_env(cls) -> "BridgeConfig":
        stored: dict[str, Any] = {}
        config_path = Path(os.environ.get("LIVE_INFINITA_INTEGRATIONS_FILE", "/var/lib/live-infinita/integrations.json"))
        if config_path.exists():
            with config_path.open(encoding="utf-8") as fh:
                candidate = json.load(fh)
            if isinstance(candidate, dict):
                stored = candidate
        unique_id = str(stored.get("tiktok_unique_id") or os.environ.get("TIKTOK_UNIQUE_ID", "")).strip()
        if not unique_id:
            raise RuntimeError("TIKTOK_UNIQUE_ID não configurado")
        if not unique_id.startswith("@"):
            unique_id = "@" + unique_id
        gateway_url = os.environ.get(
            "LIVE_INFINITA_TIKTOK_GATEWAY_URL",
            "http://127.0.0.1:8080/api/source/tiktok/event",
        ).strip()
        audience_url = os.environ.get(
            "LIVE_INFINITA_TIKTOK_AUDIENCE_URL",
            "http://127.0.0.1:8080/api/audience/tiktok/event",
        ).strip()
        timeout = float(os.environ.get("LIVE_INFINITA_SOURCE_TIMEOUT", "5"))
        retry = float(os.environ.get("LIVE_INFINITA_TIKTOK_RETRY_SECONDS", "30"))
        return cls(
            unique_id=unique_id,
            gateway_url=gateway_url,
            audience_url=audience_url,
            timeout_seconds=timeout,
            retry_seconds=max(retry, 5.0),
            sign_api_key=str(stored.get("tiktok_sign_api_key") or "") or None,
            status_file=Path(os.environ.get(
                "LIVE_INFINITA_TIKTOK_STATUS_FILE",
                "/var/lib/live-infinita/tiktok-status.json",
            )),
        )


def write_status(config: BridgeConfig, state: str, **fields: Any) -> None:
    payload = {"state": state, "unique_id": config.unique_id,
               "updated_at_unix": time.time(), **fields}
    try:
        config.status_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = config.status_file.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, sort_keys=True)
            fh.write("\n")
        temporary.replace(config.status_file)
    except OSError as exc:
        print(f"[tiktok] monitor indisponível ({type(exc).__name__})", file=sys.stderr, flush=True)


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"content-type": "application/json"}, method="POST")
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
    from TikTokLive.client.web.web_settings import WebDefaults
    WebDefaults.tiktok_sign_api_key = config.sign_api_key
    client = TikTokLiveClient(unique_id=config.unique_id)

    @client.on(ConnectEvent)
    async def on_connect(_: ConnectEvent) -> None:
        write_status(config, "connected", room_id=str(client.room_id or ""))
        print(f"[tiktok] conectado a {config.unique_id} room_id={client.room_id}", flush=True)

    @client.on(CommentEvent)
    async def on_comment(event: CommentEvent) -> None:
        payload = comment_to_payload(event, room_id=client.room_id)
        if not payload["text"]:
            return
        status, result = post_json(config.gateway_url, payload, config.timeout_seconds)
        accepted = bool(result.get("ok")) if isinstance(result, dict) else False
        write_status(config, "connected", room_id=str(client.room_id or ""), last_event="comment")
        print(f"[tiktok] comentário actor={payload['display_name']!r} text={payload['text']!r} http={status} accepted={accepted}", flush=True)

    async def send_audience(payload: dict[str, Any]) -> None:
        status, result = post_json(config.audience_url, payload, config.timeout_seconds)
        duplicate = bool(result.get("duplicate")) if isinstance(result, dict) else False
        write_status(config, "connected", room_id=str(client.room_id or ""), last_event=payload["kind"])
        print(
            f"[tiktok] audience kind={payload['kind']} actor={payload['display_name']!r} "
            f"http={status} duplicate={duplicate}",
            flush=True,
        )

    @client.on(JoinEvent)
    async def on_join(event: JoinEvent) -> None:
        await send_audience(join_to_payload(event, room_id=client.room_id))

    @client.on(LikeEvent)
    async def on_like(event: LikeEvent) -> None:
        await send_audience(like_to_payload(event, room_id=client.room_id))

    @client.on(GiftEvent)
    async def on_gift(event: GiftEvent) -> None:
        # Gifts em streak geram eventos intermediários. Só persiste o fechamento da sequência.
        if bool(getattr(event, "streaking", False)):
            return
        await send_audience(gift_to_payload(event, room_id=client.room_id))

    @client.on(DisconnectEvent)
    async def on_disconnect(_: DisconnectEvent) -> None:
        write_status(config, "disconnected")
        print("[tiktok] desconectado", flush=True)

    @client.on(LiveEndEvent)
    async def on_live_end(_: LiveEndEvent) -> None:
        write_status(config, "live_ended")
        print("[tiktok] live encerrada", flush=True)

    return client


def main() -> int:
    try:
        config = BridgeConfig.from_env()
    except Exception as exc:
        print(f"[tiktok] configuração inválida: {exc}", file=sys.stderr, flush=True)
        return 2

    print(
        f"[tiktok] bridge configurado {config.unique_id} -> comments={config.gateway_url} audience={config.audience_url}",
        flush=True,
    )

    try:
        write_status(config, "searching")
        print(f"[tiktok] procurando LIVE de {config.unique_id}...", flush=True)
        client = build_client(config)
        client.run()
        write_status(config, "waiting_retry", retry_seconds=round(config.retry_seconds))
        print("[tiktok] conexão encerrada; o serviço fará uma nova tentativa", flush=True)
        return 75
    except KeyboardInterrupt:
        write_status(config, "stopped")
        print("[tiktok] encerrado", flush=True)
        return 0
    except Exception as exc:
        name = type(exc).__name__
        message = str(exc).replace("\n", " ")
        write_status(config, "waiting_retry", error_type=name,
                     retry_seconds=round(config.retry_seconds))
        print(f"[tiktok] LIVE indisponível ou consulta recusada ({name}): {message}", flush=True)
        print("[tiktok] o serviço fará uma nova tentativa em um processo limpo", flush=True)
        return 75


if __name__ == "__main__":
    raise SystemExit(main())
