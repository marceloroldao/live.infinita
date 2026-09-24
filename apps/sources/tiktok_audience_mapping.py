from __future__ import annotations

import time
from typing import Any


def _scalar(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _actor(event: Any) -> tuple[str, str]:
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
    return str(actor_id), str(display_name)


def _event_id(event: Any, prefix: str) -> str:
    common = getattr(event, "common", None)
    value = getattr(common, "msg_id", None) or getattr(common, "message_id", None)
    return str(value or f"{prefix}-{time.time_ns()}")


def join_to_payload(event: Any, room_id: Any = None) -> dict[str, Any]:
    actor_id, display_name = _actor(event)
    return {
        "source_event_id": _event_id(event, "join"),
        "actor_id": actor_id,
        "display_name": display_name,
        "kind": "join",
        "metadata": {"event_type": "join", "room_id": _scalar(room_id), "bridge": "TikTokLive"},
    }


def like_to_payload(event: Any, room_id: Any = None) -> dict[str, Any]:
    actor_id, display_name = _actor(event)
    like_count = getattr(event, "count", None)
    if like_count is None:
        like_count = getattr(event, "like_count", None)
    total_likes = getattr(event, "total", None)
    if total_likes is None:
        total_likes = getattr(event, "total_likes", None)
    return {
        "source_event_id": _event_id(event, "like"),
        "actor_id": actor_id,
        "display_name": display_name,
        "kind": "like",
        "metadata": {
            "event_type": "like",
            "room_id": _scalar(room_id),
            "like_count": _scalar(like_count),
            "total_likes": _scalar(total_likes),
            "bridge": "TikTokLive",
        },
    }


def gift_to_payload(event: Any, room_id: Any = None) -> dict[str, Any]:
    actor_id, display_name = _actor(event)
    gift = getattr(event, "gift", None)
    return {
        "source_event_id": _event_id(event, "gift"),
        "actor_id": actor_id,
        "display_name": display_name,
        "kind": "gift",
        "metadata": {
            "event_type": "gift",
            "room_id": _scalar(room_id),
            "gift_id": _scalar(getattr(event, "gift_id", None) or getattr(gift, "id", None)),
            "gift_name": _scalar(getattr(gift, "name", None)),
            "gift_type": _scalar(getattr(gift, "type", None)),
            "repeat_count": _scalar(getattr(event, "repeat_count", None)),
            "repeat_end": _scalar(getattr(event, "repeat_end", None)),
            "diamond_count": _scalar(getattr(gift, "diamond_count", None)),
            "bridge": "TikTokLive",
        },
    }
