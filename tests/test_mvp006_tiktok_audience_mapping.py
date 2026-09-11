from __future__ import annotations

import unittest
from types import SimpleNamespace

from apps.sources.tiktok_audience_mapping import gift_to_payload, join_to_payload, like_to_payload


class MVP006TikTokAudienceMappingTest(unittest.TestCase):
    def user(self):
        return SimpleNamespace(unique_id="viewer01", nickname="Viewer 01")

    def common(self, msg_id="1001"):
        return SimpleNamespace(msg_id=msg_id)

    def test_join_mapping(self):
        event = SimpleNamespace(user=self.user(), common=self.common("join-1"))
        payload = join_to_payload(event, room_id="room-1")
        self.assertEqual(payload["kind"], "join")
        self.assertEqual(payload["actor_id"], "viewer01")
        self.assertEqual(payload["metadata"]["room_id"], "room-1")

    def test_like_mapping(self):
        event = SimpleNamespace(user=self.user(), common=self.common("like-1"), count=7, total=99)
        payload = like_to_payload(event, room_id="room-1")
        self.assertEqual(payload["kind"], "like")
        self.assertEqual(payload["metadata"]["like_count"], 7)
        self.assertEqual(payload["metadata"]["total_likes"], 99)

    def test_gift_mapping(self):
        gift = SimpleNamespace(id=5655, name="Rose", type=1, diamond_count=1)
        event = SimpleNamespace(
            user=self.user(), common=self.common("gift-1"), gift=gift,
            gift_id=5655, repeat_count=3, repeat_end=1,
        )
        payload = gift_to_payload(event, room_id="room-1")
        self.assertEqual(payload["kind"], "gift")
        self.assertEqual(payload["metadata"]["gift_name"], "Rose")
        self.assertEqual(payload["metadata"]["repeat_count"], 3)


if __name__ == "__main__":
    unittest.main()
