#!/usr/bin/env python3
"""Physical pattern experiment using the pinned core, reopened isolated SQLite."""
import argparse
import json
import hashlib
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from run_physical_memory_comparison_008ed import SDK, SDK_COMMIT, ENGINE, canonical, observation_id

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tests/godot_navigation_patterns_008eg.gd"

def run(project, fixture, recall=None):
    env = dict(os.environ, LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture))
    env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL", None)
    if recall is not None:
        env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"] = str(recall)
    p = subprocess.run([ENGINE, "--headless", "--audio-driver", "Dummy", "--path", str(project),
                        "--script", str(SCRIPT), "--", "--offline-tour"],
                       env=env, capture_output=True, text=True, timeout=60)
    log = p.stdout + p.stderr
    if p.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:", log, re.M):
        raise RuntimeError(log[-4000:])
    rows = [json.loads(x.split(" ", 1)[1]) for x in p.stdout.splitlines()
            if x.startswith("008EG_PATTERN_COMPARISON ")]
    if len(rows) != 1 or rows[0]["failures"]:
        raise RuntimeError("Pattern comparison missing or failed")
    return rows[0], log

def compare(project):
    if not SDK.is_dir():
        raise RuntimeError("Pinned real core unavailable; no synthetic fallback")
    sys.path.insert(0, str(SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService, attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008eg-patterns-") as raw:
        tmp = pathlib.Path(raw)
        fixture = tmp / "fixture.json"
        first, first_log = run(project, fixture)
        original = json.loads(fixture.read_text())
        assert original["scope"] == "isolated_actual_journeys_pattern_evidence"
        training = original["rows"]
        assert len(training) == 4
        key = "isolated-patterns-test-" + "x" * 32
        def connect():
            service = ProductStructuralObservationService.open(tmp / "core", backend="sqlite", allow_fallback=False)
            app = FastAPI()
            attach_structural_observation_routes(app, api_key=key, service=service)
            return service, TestClient(app)
        service, client = connect()
        stored = {}
        for sequence, row in enumerate(training, 1):
            measured = row["measurement"]
            assert measured["arrived"] and measured["collisions"] == 0 and measured["rescues"] == 0
            assert row["contains_prediction"] is False and row["physical_attempt"] is True
            encoded = canonical(row)
            event = {"version": 1, "source_id": "live.infinita:isolated-pattern-008eg",
                     "sequence": sequence, "byte_offset": 0, "byte_length": len(encoded),
                     "trail": [int.from_bytes(hashlib.blake2b(row["context"].encode(), digest_size=8).digest(), "big") & ((1 << 63)-1)],
                     "relation_ids": [1], "signature": hashlib.blake2b(encoded, digest_size=8).hexdigest(), "resolution": 1}
            payload = {"event": event, "provenance": {
                "hierarchy_id": "live:isolated:pattern-008eg:nov",
                "source_kind": "isolated_actual_journey_pattern_evidence",
                "world_write_authority": False, "contains_prediction": False,
                "physical_row_sha256": hashlib.sha256(encoded).hexdigest(),
                "promotion_gate_bypassed_for_isolated_transport_test": True, "row": row}}
            response = client.post("/api/v1/structural/observations?defer_associations=true",
                                   json=payload, headers={"X-Memoria-Key": key})
            assert response.status_code == 201, response.text
            ack = response.json()
            assert ack["stored"] and ack["backend"] == "sqlite" and not ack["semantic_projection"]
            assert ack["observation_id"] == observation_id(event)
            stored[ack["observation_id"]] = payload
        client.close()
        del service
        reopened, client = connect()
        response = client.get("/api/v1/structural/observations/recent?limit=100", headers={"X-Memoria-Key": key})
        assert response.status_code == 200 and not response.json()["semantic_projection"]
        items = response.json()["items"]
        assert reopened.store.count == len(stored) == len(items)
        entries = []
        for item in items:
            expected = stored[item["observation_id"]]
            assert canonical(item["event"]) == canonical(expected["event"])
            assert canonical(item["provenance"]) == canonical(expected["provenance"])
            entries.append(dict(item["provenance"]["row"], observation_id=item["observation_id"]))
        client.close()
        recall = tmp / "recovered.json"
        recall.write_text(json.dumps({"entries": entries}))
        second, second_log = run(project, fixture, recall)
        baseline = next(x for x in second["runs"] if x["arm"] == "perception")
        core = next(x for x in second["runs"] if x["arm"] == "verified_core_patterns")
        assert core["recommendation"]["source"] == "recovered-pattern-evidence"
        assert set(core["recommendation"]["observation_ids"]) <= set(stored)
        result = {"schema": "live-infinita-navigation-pattern-comparison/v1",
                  "scope": "isolated_actual_journeys_pattern_evidence_with_real_core",
                  "sdk_commit": SDK_COMMIT, "backend": "sqlite", "core_reopened": True,
                  "stored_and_recovered_observation_ids": list(stored),
                  "cold_run": first, "comparison": second,
                  "core_minus_perception_distance_m": core["distance_m"] - baseline["distance_m"],
                  "core_minus_perception_simulated_seconds": core["simulated_seconds"] - baseline["simulated_seconds"],
                  "production_learning_demonstrated": False,
                  "promotion_gate_bypassed_for_isolated_transport_test": True,
                  "limitations": [
                      "Application encodes relative sensor signatures and scores actual outcome samples.",
                      "Core stores/retrieves observations; this does not prove core autonomously learns navigation patterns.",
                      "Only translated deterministic wall fixtures and changed destination; not broad generalization.",
                      "Same local observation can hide different distant openings; mirrored case tests this aliasing.",
                      "No live services or production memory state modified."]}
        return result, first_log, second_log

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=pathlib.Path("/home/etbra/008bz-godot-test"))
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result, first, second = compare(args.project)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for name, value in [("NAVIGATION_PATTERNS_RESULT_008EG.json", json.dumps(result, indent=2)+"\n"),
                        ("NAVIGATION_PATTERNS_COLD_008EG.txt", first),
                        ("NAVIGATION_PATTERNS_CORE_008EG.txt", second)]:
        (args.output_dir/name).write_text(value)
    print(json.dumps(result, indent=2))
if __name__ == "__main__":
    main()
