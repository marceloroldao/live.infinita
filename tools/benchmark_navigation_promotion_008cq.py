"""Physical repeat experiment through RAM promotion and real API in temporary SQLite."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CORE = "/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src"

def verify_promotions(data):
    evidence = data["promotion_evidence_actions"]
    rows = data["promotions"]["entries"]
    for row in rows:
        for identity in row["decision_ids"]:
            action = evidence[identity]
            session, serial = identity.split(":")
            assert action["working_memory_session"] == session
            assert int(action["decision_serial"]) == int(serial)
            assert action["working_memory_key"] == row["summary"]["key"]
            assert action["working_memory_changed_choice"] is True
            assert action["outcome"] in ("step_reached", "goal_reached")
            assert action["collisions"] == 0
            assert math.dist(action["end"], action["selected"]) <= 0.03
            assert math.dist(action["selected"], action["perception"]["without_working_memory"]) > 0.05
            assert math.dist(action["selected"], row["summary"]["to"]) <= 0.05
    return len(rows)

def validate_environment(data):
    expected = {(variant,mode,trial) for variant in
        ("unchanged_U","opened_U","remembered_step_blocked")
        for mode in ("without_memory","with_memoria") for trial in (1,2)}
    rows = data["results"]
    assert len(rows)==12
    keyed = {(r["variant"],r["mode"],r["trial"]):r for r in rows}
    assert set(keyed)==expected
    for variant,mode,trial in expected:
        row = keyed[(variant,mode,trial)]
        assert row["reached"] is True and row["collisions"]==0
        assert row["remaining_goal_m"]<0.1
        if trial==1:
            assert row==dict(keyed[(variant,mode,2)],trial=1)
    for mode in ("without_memory","with_memoria"):
        row=keyed[("opened_U",mode,1)]
        assert abs(row["distance_m"]-6.0)<0.001 and row["revisited_end_cells"]==0
        assert row["distance_away_from_goal_m"]<0.001
    rejected=keyed[("remembered_step_blocked","with_memoria",1)]
    assert rejected["rejected_remembered_candidates"]>=1
    assert math.dist(rejected["first_selected"],data["remembered_start_step"])>0.05
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--core-src", default=CORE)
    parser.add_argument("--godot-project", required=True)
    parser.add_argument("--engine", default="/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64")
    parser.add_argument("--report", required=True)
    parser.add_argument("--environment-report", help="Optional changed-obstacle experiment using the same actual recall")
    args = parser.parse_args()
    project = Path(args.godot_project).resolve()
    if project == (ROOT/"apps/renderer-godot").resolve() or project.is_relative_to(Path("/opt/live.infinita")):
        raise ValueError("Use an isolated imported project")
    # Verify the isolated fixture actually contains the current tested navigator.
    source_hashes = {}
    for name in ("nov_navigation_experience.gd", "nov_navigation_working_memory.gd",
                 "nov_navigation_episodes.gd", "world_map_local_motion.gd", "world_map_traversability.gd"):
        raw = (ROOT/"apps/renderer-godot"/name).read_bytes()
        assert (project/name).read_bytes() == raw, name
        source_hashes[name] = sha256(raw).hexdigest()
    sys.path[:0] = [args.core_src, str(ROOT/"apps/world-runtime")]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import memoria_resolutiva.product_structural as product
    import nov_navigation_promotion_sync as promotion
    import nov_navigation_recall_export as recall
    for module in (product, promotion, recall):
        source_hashes[module.__name__] = sha256(Path(module.__file__).read_bytes()).hexdigest()
    key = "isolated-promotion-test-"+"x"*40
    world_id = "navigation-promotion-008cq"
    def app_for(service):
        app = FastAPI()
        product.attach_structural_observation_routes(app, api_key=key, service=service)
        return app
    def simulate(path, cache=None):
        command = [args.engine, "--headless", "--audio-driver", "Dummy", "--path", str(project),
                   "--script", str(ROOT/"tests/godot_navigation_promotion_benchmark_008cq.gd"),
                   "--", "--offline-tour", "--report="+str(path)]
        if cache:
            command.append("--recall="+str(cache))
        run = subprocess.run(command, capture_output=True, text=True, timeout=60)
        output = run.stdout+run.stderr
        if run.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:", output, re.M):
            raise RuntimeError(output)
        return json.loads(path.read_text())
    with tempfile.TemporaryDirectory(prefix="nov-promotion-008cq-") as directory:
        temp = Path(directory)
        first = simulate(temp/"first.json")
        assert all(row["reached"] for row in first["results"]), "A fixture failed to arrive"
        count = verify_promotions(first)
        assert count > 0, "No naturally generated eligible promotions"
        source = temp/"promotions.json"
        source.write_text(json.dumps(first["promotions"]))
        validated = promotion.read_source(source, world_id)
        assert len(validated) == count
        world = temp/"world.json"
        world.write_text(json.dumps({"world_id": world_id}))
        memory_root = temp/"memory"
        service = product.ProductStructuralObservationService.open(memory_root, backend="sqlite",
            allow_fallback=False, replay_associations_on_open=False)
        checkpoint = temp/"checkpoint.json"
        receipts = []
        with TestClient(app_for(service)) as client:
            def send(value):
                response = client.post("/api/v1/structural/observations?defer_associations=true",
                    json=value, headers={"X-Memoria-Key": key})
                assert response.status_code == 201, response.text
                receipts.append(response.json())
                return response.json()
            while promotion.sync_once(source, world, checkpoint, send)["acked"]:
                pass
            assert promotion.sync_once(source, world, checkpoint, send)["acked"] == 0
        assert len(receipts) == count
        reopened = product.ProductStructuralObservationService.open(memory_root, backend="sqlite",
            allow_fallback=False, replay_associations_on_open=False)
        cache = temp/"public"/"recall.json"
        with TestClient(app_for(reopened)) as client:
            def fetch():
                response = client.get("/api/v1/structural/observations/recent?limit=64",
                    headers={"X-Memoria-Key": key})
                assert response.status_code == 200, response.text
                return response.json()
            exported = recall.export_once(world, temp/"private.json", cache, fetch=fetch)
        if args.environment_report:
            environment_path = Path(args.environment_report)
            command = [args.engine, "--headless", "--audio-driver", "Dummy", "--path", str(project),
                "--script", str(ROOT/"tests/godot_navigation_environment_benchmark_008cs.gd"),
                "--", "--offline-tour", "--recall="+str(cache), "--report="+str(environment_path)]
            run = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if run.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:", run.stdout+run.stderr, re.M):
                raise RuntimeError(run.stdout+run.stderr)
            environment = json.loads(environment_path.read_text())
            environment["validation_passed"] = validate_environment(environment)
            environment["source_hashes"] = source_hashes
            environment["api_recovered"] = exported["cached"]
            environment["promotions_verified"] = count
            environment_path.write_text(json.dumps(environment, indent=2)+"\n")
        cached = json.loads(cache.read_text())
        assert {row["observation_id"] for row in cached["entries"]} == {r["observation_id"] for r in receipts}
        second = simulate(temp/"second.json", cache)
        off = [r for r in first["results"] if r["mode"] == "without_memory"]
        control = [r for r in second["results"] if r["mode"] == "without_memory"]
        assert off == control and off[0]["distance_m"] == off[1]["distance_m"]
        after = [r for r in second["results"] if r["mode"] == "after_restart_memoria"]
        assert len(after) == 2 and after[0] == dict(after[1], trial=1)
        assert all(row["reached"] for row in after)
        recovered_ids = {r["observation_id"] for r in receipts}
        for row in after:
            assert row["causal_memoria_decisions"] == row["verified_causal_memoria_actions"]
            assert set(row["selected_observation_ids"]).issubset(recovered_ids)
        baseline = off[0]
        final_ram = [r for r in first["results"] if r["mode"] == "ram_training"][-1]
        def difference(row):
            return {name: row[name]-baseline[name] for name in ("distance_m", "simulated_seconds", "collisions", "decisions")}
        report = {
            "schema": "live-infinita-navigation-promotion-benchmark/v1",
            "scope": "isolated_physics_production_RAM_and_real_core_API_temporary_SQLite",
            "fixture": "physical-U", "fixed_delta_seconds": 0.1, "speed_mps": 4.0,
            "production_memory_written": False, "world_write_authority": False,
            "memory_seed": "only_actual_completed_actions_no_injected_route",
            "source_hashes": source_hashes, "control_reproduced": True,
            "sqlite_reopened": True, "fresh_navigator_after_recall": True,
            "promotions_verified": count, "api_acks": len(receipts),
            "api_recovered": exported["cached"],
            "training_results": first["results"], "after_restart_results": after,
            "difference_from_cold_control": {"final_ram": difference(final_ram), "after_restart_memoria": difference(after[0])},
            "promotion_evidence": first["promotions"],
            "promotion_evidence_actions": first["promotion_evidence_actions"],
            "limitations": ["Single deterministic synthetic obstacle and fixed terrain.",
                "Simulated time is ticks times fixed delta, not server performance.",
                "Reused steps do not optimize a whole route; early RAM trials may be worse.",
                "Not a controlled production result or proof of generalization."]}
        Path(args.report).write_text(json.dumps(report, indent=2)+"\n")
        summary = {k:v for k,v in report.items() if k not in ("promotion_evidence", "promotion_evidence_actions", "source_hashes")}
        print(json.dumps(summary, indent=2))

if __name__ == "__main__":
    main()
