from __future__ import annotations

import time
from typing import Any


def scalar(value: Any) -> str | int | float | bool | None:
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
            "room_id": scalar(room_id),
            "bridge": "TikTokLive",
        },
    }
