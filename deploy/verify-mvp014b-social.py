#!/usr/bin/env python3
"""Read-only post-deploy gate: MVP-014b is installed but closed to unsigned input."""
from __future__ import annotations

import json
import sys
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(repo / "apps" / "world-runtime"))
from npc_social_exchange import SocialEventJournal  # noqa: E402

root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/var/lib/live-infinita/autonomous-world")
journal = SocialEventJournal(root / "npc-social-events.jsonl")
# No authenticated signer/binding ingress is enabled by this deployment.
events = journal.completed_exchanges()
if events:
    raise AssertionError("unexpected confirmed exchange without authenticated ingress")
social = root / "npc-social-evidence.jsonl"
count = 0
if social.exists():
    with social.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            assert row.get("schema") == "npc_social_evidence_v1"
            if row.get("kind") == "confirmed_exchange":
                raise AssertionError("unexpected confirmed social evidence")
            if row.get("kind") != "encounter" or row.get("confirmed") is not False:
                raise AssertionError("invalid social evidence kind")
            count += 1

shadow = root / "memoria-v2-shadow.jsonl"
with shadow.open("rb") as fh:
    fh.seek(0, 2)
    fh.seek(max(0, fh.tell() - 256_000))
    lines = fh.readlines()[-20:]
matches = 0
for raw in lines:
    try:
        row = json.loads(raw)
    except ValueError:
        continue
    activity = row.get("tick_activity") or {}
    if "npc_social_exchanges" not in activity:
        continue
    assert row.get("authority") == "shadow-observer"
    assert row.get("world_mutated_by_shadow") is False
    assert (row.get("contextual_forecast") or {}).get("predicts_action") is False
    matches += 1
assert matches, "new social-exchange shadow contract not observed"
print("MVP014B_GATE_OK", "encounter_records="+str(count),
      "confirmed_exchanges="+str(len(events)), "shadow_contract_records="+str(matches))
