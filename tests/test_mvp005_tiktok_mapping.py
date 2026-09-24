from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SOURCES_DIR = ROOT / "apps" / "sources"
if str(SOURCES_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCES_DIR))

from tiktok_mapping import comment_to_payload  # noqa: E402


class MVP005TikTokMappingTest(unittest.TestCase):
    def test_comment_maps_to_universal_source_payload(self) -> None:
        event = SimpleNamespace(
            comment="noite",
            user=SimpleNamespace(unique_id="viewer42", nickname="Viewer 42"),
            common=SimpleNamespace(msg_id=123456789),
        )

        payload = comment_to_payload(event, room_id=987654)

        self.assertEqual(payload["source_event_id"], "123456789")
        self.assertEqual(payload["actor_id"], "viewer42")
        self.assertEqual(payload["display_name"], "Viewer 42")
        self.assertEqual(payload["text"], "noite")
        self.assertEqual(payload["metadata"]["event_type"], "comment")
        self.assertEqual(payload["metadata"]["room_id"], 987654)
        self.assertEqual(payload["metadata"]["bridge"], "TikTokLive")

    def test_comment_is_trimmed_and_actor_falls_back(self) -> None:
        event = SimpleNamespace(
            comment="  dia  ",
            user=SimpleNamespace(id=77, nickname=""),
            common=SimpleNamespace(message_id="msg-77"),
        )

        payload = comment_to_payload(event)

        self.assertEqual(payload["source_event_id"], "msg-77")
        self.assertEqual(payload["actor_id"], "77")
        self.assertEqual(payload["display_name"], "77")
        self.assertEqual(payload["text"], "dia")


if __name__ == "__main__":
    unittest.main()
