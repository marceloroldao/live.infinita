"""Store native physical pattern outcomes and export verified recovered evidence."""
from __future__ import annotations
from hashlib import blake2b, sha256
import json
import math
from pathlib import Path
import re
import time
from nov_spatial_memory_sync import _canonical, _post_local, _validate_ack, _observation_id, _world_id
from nov_navigation_memory_sync import write_checkpoint
from nov_navigation_recall_export import fetch_recent

PROFILE = "capsule044-height18-lookahead3-contour64-localexit-v2"
SCHEMA = "live-infinita-native-pattern-outcomes/v2"
RECALL_SCHEMA = "live-infinita-native-pattern-recall/v2"
SOURCE = Path("/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-navigation-patterns-008ei.json")
WORLD = Path("/var/lib/live-infinita/autonomous-world/world.json")
CHECKPOINT = Path("/var/lib/live-infinita/memoria-local/navigation-pattern-checkpoint-008ei.json")
RECALL = Path("/var/lib/live-infinita/memoria-local/navigation-pattern-recall-008ei.json")
LIMIT = 512
FIELDS = {"attempt_id", "world_id", "observer", "profile", "context", "side", "outcome",
          "distance_m", "initial_remaining_m", "physical_attempt", "contains_prediction",
          "ended_at_unix", "exploration", "completion_basis", "exit_progress_m"}

class PatternSyncError(RuntimeError):
    pass

def read_json(path):
    if path.is_symlink() or path.stat().st_size > 1_000_000:
        raise PatternSyncError("invalid_bounded_file")
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise PatternSyncError("invalid_document")
    return data

def validate(row):
    if not isinstance(row, dict) or set(row) != FIELDS:
        raise PatternSyncError("invalid_outcome_fields")
    world = row["world_id"]
    if not isinstance(world, str) or not world or len(world) > 200 or row["observer"] != "nov" or row["profile"] != PROFILE:
        raise PatternSyncError("invalid_scope")
    if not isinstance(row["attempt_id"], str) or not 1 <= len(row["attempt_id"]) <= 300:
        raise PatternSyncError("invalid_attempt")
    signature = re.fullmatch(re.escape(PROFILE+"|"+world+"|")+"local-clear-v1:(\\d+):(\\d+)", row["context"])
    if signature is None or any(not 0 <= int(v) <= 255 for v in signature.groups()):
        raise PatternSyncError("invalid_context")
    if type(row["side"]) not in (int, float) or row["side"] not in (-1, 1) or row["outcome"] not in ("contour_completed", "blocked", "stuck_recovery"):
        raise PatternSyncError("invalid_action_outcome")
    if row["physical_attempt"] is not True or row["contains_prediction"] is not False or type(row["exploration"]) is not bool:
        raise PatternSyncError("invalid_fact_markers")
    for field in ("distance_m", "initial_remaining_m", "ended_at_unix", "exit_progress_m"):
        v = row[field]
        if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
            raise PatternSyncError("invalid_measurement")
    if row["distance_m"] > 1e7 or not 0 < row["initial_remaining_m"] <= 1e7 or row["ended_at_unix"] <= 0:
        raise PatternSyncError("measurement_bound")
    basis = row["completion_basis"]
    if row["outcome"] == "contour_completed":
        if basis not in ("executed_exit", "goal_reached") or (basis == "executed_exit" and row["exit_progress_m"] < 0.75):
            raise PatternSyncError("unexecuted_exit")
    elif basis != ("physical_collision" if row["outcome"] == "blocked" else "stuck_recovery"):
        raise PatternSyncError("invalid_failure_basis")
    return dict(row, side=int(row["side"]))

def payload(row):
    validate(row)
    encoded = _canonical(row)
    digest = sha256(encoded).hexdigest()
    event = {"version": 1, "source_id": "live.infinita:native-pattern-v2:"+digest,
             "sequence": 1, "byte_offset": 0, "byte_length": len(encoded),
             "trail": [int.from_bytes(blake2b(str(row[k]).encode(), digest_size=8).digest(), "big") & ((1<<63)-1)
                       for k in ("context", "side", "outcome")],
             "relation_ids": [1], "signature": blake2b(encoded, digest_size=8).hexdigest(), "resolution": 1}
    return {"event": event, "provenance": {
        "hierarchy_id": "live:patterns:"+row["world_id"]+":nov:"+PROFILE,
        "source_kind": "native_physical_pattern_outcome",
        "world_id": row["world_id"], "entity_id": "nov", "profile": PROFILE,
        "world_write_authority": False, "contains_prediction": False,
        "outcome_sha256": digest, "outcome": row}}

def sync_once(source=SOURCE, world=WORLD, checkpoint=CHECKPOINT, recall=RECALL,
              send=_post_local, fetch=fetch_recent, now=time.time, limit=4):
    if type(limit) is not int or not 1 <= limit <= 4:
        raise PatternSyncError("invalid_limit")
    world_id = _world_id(world)
    snapshot = read_json(source)
    if snapshot.get("schema") != SCHEMA or snapshot.get("profile") != PROFILE or not isinstance(snapshot.get("rows"), list) or len(snapshot["rows"]) > LIMIT:
        raise PatternSyncError("invalid_snapshot")
    rows = [validate(row) for row in snapshot["rows"]]
    by_attempt = {}
    for row in rows:
        if row["attempt_id"] in by_attempt:
            raise PatternSyncError("duplicate_attempt_in_snapshot")
        by_attempt[row["attempt_id"]] = row
    rows = [row for row in rows if row["world_id"] == world_id]
    state = {"world_id": world_id, "seen": {}, "confirmed": 0}
    if checkpoint.exists():
        old = read_json(checkpoint)
        if old.get("world_id") == world_id:
            if not isinstance(old.get("seen"), dict) or len(old["seen"]) > LIMIT or type(old.get("confirmed")) is not int:
                raise PatternSyncError("invalid_checkpoint")
            state = old
    state["seen"] = {k: v for k, v in state["seen"].items() if k in {r["attempt_id"] for r in rows}}
    acked = 0
    for row in rows:
        request = payload(row)
        expected = _observation_id(request["event"])
        prior = state["seen"].get(row["attempt_id"])
        if prior is not None:
            if prior != expected:
                raise PatternSyncError("attempt_fact_changed")
            continue
        receipt = send(request)
        _validate_ack(receipt, request)
        if receipt["backend"] != "sqlite" or receipt["stored"] == receipt["duplicate"]:
            raise PatternSyncError("durable_sqlite_receipt_required")
        state["seen"][row["attempt_id"]] = expected
        state["confirmed"] += 1
        write_checkpoint(checkpoint, state)
        acked += 1
        if acked == limit:
            break
    # Recover actual API envelopes, not submitted rows or ACKs as substitutes.
    response = fetch()
    if not isinstance(response, dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"), list) or len(response["items"]) > 100:
        raise PatternSyncError("invalid_recovery")
    recovered = {}
    if recall.exists():
        old = read_json(recall)
        if old.get("schema") == RECALL_SCHEMA and old.get("world_id") == world_id:
            if not isinstance(old.get("entries"), list) or len(old["entries"]) > LIMIT:
                raise PatternSyncError("invalid_recall_cache")
            for entry in old["entries"]:
                fact = dict(entry)
                identity = fact.pop("observation_id", "")
                validate(fact)
                if identity != _observation_id(payload(fact)["event"]):
                    raise PatternSyncError("cached_identity_invalid")
                recovered[fact["attempt_id"]] = entry
    fetched = 0
    for envelope in response["items"]:
        if not isinstance(envelope, dict):
            raise PatternSyncError("invalid_envelope")
        provenance = envelope.get("provenance", {})
        if provenance.get("source_kind") != "native_physical_pattern_outcome" or provenance.get("world_id") != world_id:
            continue
        fact = validate(provenance.get("outcome"))
        expected = payload(fact)
        if _canonical(envelope.get("event")) != _canonical(expected["event"]) or _canonical(provenance) != _canonical(expected["provenance"]) or envelope.get("observation_id") != _observation_id(expected["event"]):
            raise PatternSyncError("recovered_fact_identity_mismatch")
        prior = recovered.get(fact["attempt_id"])
        if prior is not None and prior != dict(fact, observation_id=envelope["observation_id"]):
            raise PatternSyncError("conflicting_recovered_attempt")
        recovered[fact["attempt_id"]] = dict(fact, observation_id=envelope["observation_id"])
        fetched += 1
    entries = sorted(recovered.values(), key=lambda r: (r["ended_at_unix"], r["attempt_id"]))[-LIMIT:]
    result = {"schema": RECALL_SCHEMA, "world_id": world_id, "generated_at_unix": now(),
              "world_write_authority": False, "entries": entries}
    write_checkpoint(recall, result)
    return {"acked": acked, "confirmed": state["confirmed"], "recovered_this_poll": fetched,
            "cached_recovered": len(entries), "world_write_authority": False}

if __name__ == "__main__":
    try:
        print(json.dumps(sync_once(), sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1)
