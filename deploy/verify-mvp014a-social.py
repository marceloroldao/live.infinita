#!/usr/bin/env python3
"""Read-only postdeploy gate for MVP-014a social evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/var/lib/live-infinita/autonomous-world")
ledger = root / "npc-social-evidence.jsonl"
shadow = root / "memoria-v2-shadow.jsonl"

rows = []
if ledger.exists():
    with ledger.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
seen = set()
for row in rows:
    assert row.get("schema") == "npc_social_evidence_v1"
    key = row.get("evidence_id")
    assert isinstance(key, str) and key not in seen
    seen.add(key)
    if row.get("kind") == "encounter":
        assert row.get("confirmed") is False
        assert row.get("status") == "observed_unconfirmed"
        assert row.get("satisfaction_delta") == 0
    elif row.get("kind") == "confirmed_exchange":
        # Production has no authoritative exchange producer yet.
        raise AssertionError("unexpected confirmed social exchange")
    else:
        raise AssertionError("unexpected social evidence kind")

with shadow.open("rb") as fh:
    # Bounded tail without scanning the growing historical shadow ledger.
    fh.seek(0, 2)
    size = fh.tell()
    fh.seek(max(0, size - 128_000))
    latest = fh.readlines()[-10:]
matches = 0
for line in latest:
    try:
        item = json.loads(line)
    except ValueError:
        continue
    activity = item.get("tick_activity") or {}
    if "npc_social_evidence" not in activity:
        continue
    assert item.get("authority") == "shadow-observer"
    assert item.get("world_mutated_by_shadow") is False
    forecast = item.get("contextual_forecast") or {}
    assert forecast.get("predicts_action") is False
    matches += 1
assert matches > 0, "new shadow contract not observed yet"
print("SOCIAL_EVIDENCE_GATE_OK", "records="+str(len(rows)), "shadow_new_contract="+str(matches))
