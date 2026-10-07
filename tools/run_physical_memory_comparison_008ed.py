#!/usr/bin/env python3
"""Isolated real-capsule comparison with the pinned real core and fresh SQLite."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SDK_COMMIT = "dfd87c995b50c49b45a9d5dd4c43cce456983d4f"
SDK = pathlib.Path("/opt/live-infinita-memoria-core") / SDK_COMMIT / "src"
SCRIPT = ROOT / "tests/godot_physical_memory_comparison_008ed.gd"
ENGINE = "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64"

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()

def observation_id(event):
    normalized = {k: event[k] for k in ("version", "source_id", "sequence", "byte_offset",
                                       "byte_length", "trail", "relation_ids", "signature", "resolution")}
    return "structural-event:" + hashlib.blake2b(canonical(normalized), digest_size=20).hexdigest()

def run_godot(project, fixture, recall=None):
    env = dict(os.environ, LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture))
    env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL", None)
    if recall is not None:
        env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"] = str(recall)
    result = subprocess.run([ENGINE, "--headless", "--audio-driver", "Dummy", "--path", str(project),
                             "--script", str(SCRIPT),
                             "--", "--offline-tour"], capture_output=True, text=True, timeout=60, env=env)
    log = result.stdout + result.stderr
    if result.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:", log, re.M):
        raise RuntimeError("Godot physical comparison failed: " + log[-3000:])
    records = [json.loads(line.split(" ", 1)[1]) for line in result.stdout.splitlines()
               if line.startswith("008ED_PHYSICAL_COMPARISON ")]
    if len(records) != 1 or records[0]["failures"]:
        raise RuntimeError("physical comparison result missing or failed")
    return records[0], log

def compare(project):
    if not SDK.is_dir():
        raise RuntimeError("pinned real core unavailable; no synthetic fallback")
    sys.path.insert(0, str(SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService, attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008ed-physical-memory-") as raw:
        temporary = pathlib.Path(raw)
        fixture = temporary / "physical-fixture.json"
        first, first_log = run_godot(project, fixture)
        original = json.loads(fixture.read_text())
        if original["scope"] != "isolated_real_capsule_fixture" or not original["run"]["arrived"] or original["run"]["collisions"]:
            raise RuntimeError("incomplete or collision-tainted physical training")
        rows = original["rows"]
        if not rows or len(rows) > 512:
            raise RuntimeError("physical training outside bounded memory")
        encoded = canonical(original)
        event = {"version": 1, "source_id": "live.infinita:isolated-physical-benchmark-008ed",
                 "sequence": 1, "byte_offset": 0, "byte_length": len(encoded),
                 "trail": [int.from_bytes(hashlib.blake2b(canonical(row["from"]), digest_size=8).digest(), "big") & ((1 << 63)-1) for row in rows],
                 "relation_ids": [1], "signature": hashlib.blake2b(encoded, digest_size=8).hexdigest(), "resolution": 1}
        payload = {"event": event, "provenance": {
            "hierarchy_id": "live:isolated:physical-benchmark-008ed:nov",
            "source_kind": "isolated_real_capsule_complete_journey",
            "world_id": original["world_id"], "entity_id": "nov",
            "world_write_authority": False, "contains_prediction": False,
            "physical_fixture_sha256": hashlib.sha256(encoded).hexdigest(),
            "promotion_gate_bypassed_for_isolated_transport_test": True, "rows": rows}}
        key = "isolated-physical-memory-test-" + "x" * 32
        def connect():
            service = ProductStructuralObservationService.open(temporary / "core", backend="sqlite", allow_fallback=False)
            app = FastAPI()
            attach_structural_observation_routes(app, api_key=key, service=service)
            return service, TestClient(app)
        service, client = connect()
        response = client.post("/api/v1/structural/observations?defer_associations=true",
                               json=payload, headers={"X-Memoria-Key": key})
        if response.status_code != 201:
            raise RuntimeError("real core store failed: " + response.text[:1000])
        ack = response.json()
        if ack["observation_id"] != observation_id(event) or ack["backend"] != "sqlite" or not ack["stored"] or ack["semantic_projection"]:
            raise RuntimeError("real core acknowledgment rejected")
        client.close()
        del service
        reopened, client = connect()
        response = client.get("/api/v1/structural/observations/recent?limit=100", headers={"X-Memoria-Key": key})
        if response.status_code != 200 or response.json()["semantic_projection"]:
            raise RuntimeError("real core retrieval failed")
        matching = [item for item in response.json()["items"] if item["observation_id"] == ack["observation_id"]]
        if len(matching) != 1 or canonical(matching[0]["provenance"]) != canonical(payload["provenance"]) or canonical(matching[0]["event"]) != canonical(event):
            raise RuntimeError("recovered physical record differs from stored evidence")
        if reopened.store.count != 1:
            raise RuntimeError("isolated core should contain only the physical fixture")
        recovered = matching[0]
        client.close()
        recall = temporary / "verified-recall.json"
        recall.write_text(json.dumps({"entries": [dict(row, observation_id=recovered["observation_id"])
                                                  for row in recovered["provenance"]["rows"]]}))
        second, second_log = run_godot(project, fixture, recall)
        baseline = next(x for x in second["runs"] if x["arm"] == "perception")
        core_run = next(x for x in second["runs"] if x["arm"] == "verified_core_recall")
        # Report measurements without forcing an expected speedup.
        result = {"schema": "live-infinita-physical-memory-comparison/v1",
                  "scope": "isolated_real_capsule_fixture_with_real_pinned_core",
                  "sdk_commit": SDK_COMMIT, "core_backend": "sqlite",
                  "core_reopened_before_retrieval": True,
                  "stored_and_recovered_observation_id": recovered["observation_id"],
                  "physical_rows_recovered": len(rows), "fixture_sha256": hashlib.sha256(encoded).hexdigest(),
                  "promotion_gate_bypassed_for_isolated_transport_test": True,
                  "cold_run": first, "comparison": second,
                  "core_minus_perception_distance_m": core_run["distance_m"] - baseline["distance_m"] if core_run["arrived"] and baseline["arrived"] else None,
                  "core_minus_perception_simulated_seconds": core_run["simulated_seconds"] - baseline["simulated_seconds"] if core_run["arrived"] and baseline["arrived"] else None,
                  "production_learning_demonstrated": False,
                  "limitations": ["One deterministic fixed wall/gap; not statistical generalization.",
                                  "Simulation time is fixed dt multiplied by ticks, not live wall time.",
                                  "RAM bonus 1.5 and recovered bonus 2.0 are existing application policy weights.",
                                  "Core stores and retrieves observations; application computes navigation choices.",
                                  "Fixture intentionally bypasses production causal-promotion eligibility.",
                                  "All data and core state are isolated; no production history or live services changed."]}
        return result, first_log, second_log

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=pathlib.Path, default=pathlib.Path("/home/etbra/008bz-godot-test"))
    parser.add_argument("--output-dir", type=pathlib.Path, required=True)
    args = parser.parse_args()
    result, first, second = compare(args.project)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "PHYSICAL_MEMORY_COMPARISON_008ED.json").write_text(json.dumps(result, indent=2)+"\n")
    (args.output_dir / "PHYSICAL_MEMORY_COLD_008ED.txt").write_text(first)
    (args.output_dir / "PHYSICAL_MEMORY_VERIFIED_CORE_008ED.txt").write_text(second)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
