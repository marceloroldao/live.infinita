"""Matched navigation arms; actual learned evidence and isolated Memoria.ia."""
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
ENGINE = "/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64"
KEY = "isolated-causality-benchmark-" + "x"*40
WORLD = "navigation-live-learning-008df"

def worker(stage, directory, core):
    sys.path[:0] = [core, str(ROOT/"apps/world-runtime")]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import memoria_resolutiva.product_structural as product
    import nov_navigation_promotion_sync as promotion
    import nov_navigation_recall_export as recall
    temp = Path(directory).resolve()
    if temp.parent!=Path(tempfile.gettempdir()).resolve() or not temp.name.startswith("nov-live-learning-008df-"):
        raise ValueError("Worker requires its isolated temporary directory")
    service = product.ProductStructuralObservationService.open(temp/"memory",backend="sqlite",
        allow_fallback=False,replay_associations_on_open=False)
    app = FastAPI()
    product.attach_structural_observation_routes(app,api_key=KEY,service=service)
    receipts = []
    with TestClient(app) as client:
        if stage=="store":
            def send(value):
                response = client.post("/api/v1/structural/observations?defer_associations=true",
                    json=value,headers={"X-Memoria-Key":KEY})
                assert response.status_code==201,response.text
                receipts.append(response.json())
                return response.json()
            while promotion.sync_once(temp/"promotions.json",temp/"world.json",temp/"checkpoint.json",send)["acked"]:
                pass
            assert promotion.sync_once(temp/"promotions.json",temp/"world.json",temp/"checkpoint.json",send)["acked"]==0
            result = {"receipts":receipts}
        else:
            def fetch():
                response = client.get("/api/v1/structural/observations/recent?limit=64",
                    headers={"X-Memoria-Key":KEY})
                assert response.status_code==200,response.text
                return response.json()
            result = recall.export_once(temp/"world.json",temp/"private.json",temp/"recall.json",fetch=fetch)
    result["source_hashes"] = {m.__name__:sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (product,promotion,recall)}
    (temp/(stage+"-stage.json")).write_text(json.dumps(result))

def run_godot(args,output,extra=()):
    command = [args.engine,"--headless","--audio-driver","Dummy","--path",args.project,
        "--script",str(ROOT/"tests/godot_live_trial_error_008df.gd"),"--","--offline-tour",
        "--report="+str(output),*extra]
    result = subprocess.run(command,capture_output=True,text=True,timeout=60)
    log = result.stdout+result.stderr
    Path(str(output)+".log").write_text(log)
    if result.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):
        raise RuntimeError(log)
    return json.loads(output.read_text())

def validate_results(rows,count,ids):
    expected = {(v,m,t) for v in ("unchanged_U","opened_U","remembered_step_blocked")
        for m in ("without_memory","with_trained_ram","after_restart_memoria") for t in (1,2)}
    assert len(rows)==18 and {(r["variant"],r["mode"],r["trial"]) for r in rows}==expected
    for row in rows:
        assert row["route_plan_builds"]==0 and row["collisions"]==0,row
        assert not row["reached"] or row["remaining_goal_m"]<0.1,row
        assert row["loaded_knowledge"]==(0 if row["mode"]=="without_memory" else count)
        assert set(row["selected_observation_ids"]).issubset(ids)
        ram = persistent = 0
        for action in row["actions"]:
            if action["outcome"] not in ("step_reached","goal_reached"):
                continue
            p = action["perception"]
            selected = action["selected"]
            baseline = p.get("without_working_memory")
            if action.get("working_memory_changed_choice") and baseline and math.dist(selected,baseline)>0.05:
                ram += 1
            baseline = p.get("without_memoria")
            if action["decision_source"]=="memoria.ia" and baseline and math.dist(selected,baseline)>0.05:
                persistent += 1
        assert ram==row["verified_causal_ram_actions"]
        assert persistent==row["verified_causal_memoria_actions"]
        if row["mode"]=="without_memory":assert ram==persistent==0
        if row["mode"]=="with_trained_ram":assert persistent==0
        if row["mode"]=="after_restart_memoria":assert ram==0
    keyed = {(r["variant"],r["mode"],r["trial"]):r for r in rows}
    for variant,mode,trial in expected:
        if trial!=1:continue
        a,b = keyed[(variant,mode,1)],keyed[(variant,mode,2)]
        for field in ("distance_m","moving_seconds","revisited_end_cells",
            "verified_causal_ram_actions","verified_causal_memoria_actions"):
            if field in a and field in b:
                assert abs(a[field]-b[field])<1e-5,(variant,mode,field)
    return True

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project")
    parser.add_argument("--engine",default=ENGINE)
    parser.add_argument("--core-src",default=CORE)
    parser.add_argument("--report")
    parser.add_argument("--internal-stage",choices=("store","recall"))
    parser.add_argument("--directory")
    args = parser.parse_args()
    if args.internal_stage:
        worker(args.internal_stage,args.directory,args.core_src)
        return
    if not args.project or not args.report:parser.error("--project and --report are required")
    project = Path(args.project).resolve()
    if project==(ROOT/"apps/renderer-godot").resolve() or project.is_relative_to(Path("/opt/live.infinita")):
        raise ValueError("Use an isolated project")
    hashes = {}
    for name in ("nov_navigation_experience.gd","nov_navigation_working_memory.gd",
        "nov_navigation_episodes.gd","nov_navigation_journey.gd","nov_observed_route.gd","world_map_local_motion.gd","world_map_traversability.gd"):
        raw = (ROOT/"apps/renderer-godot"/name).read_bytes()
        assert (project/name).read_bytes()==raw,name
        hashes[name] = sha256(raw).hexdigest()
    hashes["benchmark_godot"] = sha256((ROOT/"tests/godot_live_trial_error_008df.gd").read_bytes()).hexdigest()
    hashes["benchmark_python"] = sha256(Path(__file__).read_bytes()).hexdigest()
    from benchmark_navigation_promotion_008cq import verify_promotions
    with tempfile.TemporaryDirectory(prefix="nov-live-learning-008df-") as directory:
        temp = Path(directory).resolve()
        print("Training from actual completed physics actions",flush=True)
        training = run_godot(args,temp/"training.json")
        assert all(row["route_plan_builds"]==0 for row in training["results"])
        count = verify_promotions(training)
        assert count>0
        # Replay the same actually promoted knowledge in both arms. The latest
        # live RAM recommendation may have changed after promotion; reconstruct
        # its recommendation at promotion from the verified winning actions.
        promotions = training["promotions"]
        rows = promotions["entries"]
        assert rows
        count = len(rows)
        seed = {"world_id":WORLD,"ram_entries":{r["summary"]["key"]:{
            "to":r["summary"]["to"],"reuses":3,"evidence":r["decision_ids"],
            "last_serial":max(training["promotion_evidence_actions"][identity]["decision_serial"] for identity in r["decision_ids"]),
            "last_ms":0} for r in rows}}
        blocked = min(rows,key=lambda r:math.dist(r["summary"]["from"],[-100,0]))["summary"]
        seed["quality"]={r["summary"]["key"]+"@"+",".join(str(round(v*20)) for v in r["summary"]["to"]):r["summary"]["route_quality"] for r in rows}
        seed["blocked_from"] = blocked["from"]
        seed["blocked_to"] = blocked["to"]
        (temp/"seed.json").write_text(json.dumps(seed))
        (temp/"promotions.json").write_text(json.dumps(promotions))
        (temp/"world.json").write_text(json.dumps({"world_id":WORLD}))
        for stage in ("store","recall"):
            print("Memoria.ia isolated process: "+stage,flush=True)
            result = subprocess.run([sys.executable,__file__,"--internal-stage",stage,
                "--directory",str(temp),"--core-src",args.core_src],capture_output=True,text=True,timeout=60)
            if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        store = json.loads((temp/"store-stage.json").read_text())
        recovered = json.loads((temp/"recall.json").read_text())
        assert json.loads((temp/"recall-stage.json").read_text())["source_hashes"]==store["source_hashes"]
        receipts = store["receipts"]
        assert len(receipts)==count
        ids = {r["observation_id"] for r in receipts}
        assert {r["observation_id"] for r in recovered["entries"]}==ids
        assert {r["key"]:r["to"] for r in recovered["entries"]}=={r["summary"]["key"]:r["summary"]["to"] for r in rows}
        assert {r["key"]:r["route_quality"] for r in recovered["entries"]}=={r["summary"]["key"]:r["summary"]["route_quality"] for r in rows}
        hashes.update(store["source_hashes"])
        print("Evaluating 18 matched trials",flush=True)
        evaluation = run_godot(args,temp/"evaluation.json",("--evaluate=true","--seed="+str(temp/"seed.json"),"--recall="+str(temp/"recall.json")))
        validate_results(evaluation["results"],count,ids)
        comparisons = []
        for variant in ("unchanged_U","opened_U","remembered_step_blocked"):
            group = [r for r in evaluation["results"] if r["variant"]==variant]
            for mode in ("without_memory","with_trained_ram","after_restart_memoria"):
                selected = [r for r in group if r["mode"]==mode]
                controls = [r for r in group if r["mode"]=="without_memory"]
                mean = lambda items,key:sum(r[key] for r in items)/len(items)
                comparisons.append({"variant":variant,"mode":mode,
                    "distance_m":mean(selected,"distance_m"),
                    "difference_from_no_memory_m":mean(selected,"distance_m")-mean(controls,"distance_m"),
                    "moving_seconds":mean(selected,"moving_seconds"),
                    "causal_ram_actions":sum(r["verified_causal_ram_actions"] for r in selected),
                    "causal_memoria_actions":sum(r["verified_causal_memoria_actions"] for r in selected),
                    "revisited_end_cells":mean(selected,"revisited_end_cells"),
                    "arrivals":sum(r["reached"] for r in selected),"trials":len(selected)})
        report = {"schema":"live-infinita-navigation-live-learning-benchmark/v1",
            "scope":"isolated_current_physics_and_actual_learning_with_process_restarted_SQLite_API",
            "source_commit":subprocess.check_output(["git","-C",str(ROOT),"rev-parse","HEAD"],text=True).strip(),
            "production_memory_written":False,"world_write_authority":False,
            "fixed_delta_seconds":0.1,"speed_mps":4.0,"source_hashes":hashes,
            "same_verified_knowledge_in_ram_and_memoria":True,"eligible_shared_entries":count,
            "api_acks":len(receipts),"api_recovered":len(recovered["entries"]),
            "api_receipts":receipts,"recovered_recall":recovered,
            "separate_store_and_recall_processes":True,"fresh_planner_every_evaluation":True,
            "observed_route_search_enabled":False,"fresh_transient_state_every_training_trial":True,
            "evaluation_learning_enabled":False,"training_complete_journey_learning_enabled":True,"knowledge_seed":"same_actually_promoted_steps_replayed_in_RAM_and_recovered_from_API",
            "training_results":training["results"],"promotion_evidence":promotions,
            "promotion_evidence_actions":training["promotion_evidence_actions"],
            "evaluation_results":evaluation["results"],"comparisons":comparisons,
            "validation_passed":True,
            "limitations":["Synthetic U obstacle and flat terrain; not a controlled live measurement.",
                "Transient navigation state is reset between training trials; only learned RAM and its evidence persist.",
                "RAM recommendation at promotion is reconstructed from verified actions; latest evolving RAM can differ.",
                "Changed obstacles are finite test cases, not proof of universal generalization.",
                "Movement time uses fixed simulation ticks; planning ticks depend on CPU slicing and are reported separately."]}
        Path(args.report).write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps({"eligible_shared_entries":count,"comparisons":comparisons},indent=2))

if __name__=="__main__":main()
