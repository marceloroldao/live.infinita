#!/usr/bin/env python3
import asyncio
import json
import sys

import websockets


async def main() -> int:
    async with websockets.connect("ws://127.0.0.1:8080/ws", max_size=8_000_000) as ws:
        raw = await asyncio.wait_for(ws.recv(), timeout=5)
        message = json.loads(raw)
        world = message.get("world", {})
        interest = world.get("interest", {})
        regions = interest.get("region_descriptors", [])
        if not isinstance(regions, list) or not 1 <= len(regions) <= 16:
            print(f"REGION_DESCRIPTOR_CHECK_FAIL count={len(regions) if isinstance(regions, list) else 'invalid'}")
            return 2
        current = str(interest.get("current_region_id", ""))
        ids = [str(row.get("id", "")) for row in regions if isinstance(row, dict)]
        if current and current not in ids:
            print(f"REGION_DESCRIPTOR_CHECK_FAIL current={current} ids={ids}")
            return 3
        print(f"REGION_DESCRIPTOR_CHECK_OK current={current} count={len(regions)} ids={','.join(ids)}")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
