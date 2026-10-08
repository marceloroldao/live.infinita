#!/usr/bin/env python3
"""Paired physical comparison and changed-geometry adaptation through real isolated core."""
import argparse,json,os,pathlib,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
native.SCRIPT=native.ROOT/"tests/godot_paired_adaptation_008en.gd"
def run(project):
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008en-paired-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall,adapted=[tmp/n for n in
            ("fixture.json","state.json","world.json","checkpoint.json","recall.json","adapted.json")]
        world.write_text(json.dumps({"world_id":"native-pattern-008eh"}))
        os.environ["LIVE_INFINITA_ADAPTED_FIXTURE"]=str(adapted)
        os.environ["LIVE_INFINITA_PAIRED_PHASE"]="training"
        training,training_log=native.godot(project,fixture,state)
        assert len(json.loads(fixture.read_text())["rows"])==4
        key="isolated-paired-"+("x"*32)
        def connect():
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI()
            attach_structural_observation_routes(app,api_key=key,service=service)
            return service,TestClient(app)
        service,client=connect()
        def send(row):
            response=client.post("/api/v1/structural/observations?defer_associations=true",
                json=row,headers={"X-Memoria-Key":key})
            assert response.status_code==201,response.text
            return response.json()
        def fetch():
            response=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert response.status_code==200,response.text
            return response.json()
        intake=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch)
        assert intake["acked"]==4 and service.store.count==4
        client.close();del service
        service,client=connect();recall.unlink()
        def forbidden_send(_):raise AssertionError("Cold recovery must not reingest")
        recovered=sync_once(fixture,world,checkpoint,recall,send=forbidden_send,fetch=fetch)
        assert recovered["acked"]==0 and recovered["cached_recovered"]==4
        os.environ["LIVE_INFINITA_PAIRED_PHASE"]="paired"
        comparison,comparison_log=native.godot(project,fixture,state,recall)
        rows=json.loads(adapted.read_text())["rows"]
        assert len(rows)>4
        batches=[]
        for _ in range(20):
            batch=sync_once(adapted,world,checkpoint,recall,send=send,fetch=fetch);batches.append(batch)
            if batch["acked"]==0:break
        assert service.store.count==4+len(rows), (service.store.count,len(rows))
        expected=json.loads(recall.read_text())["entries"]
        client.close();del service
        service,client=connect();recall.unlink()
        repaired_recovery=sync_once(adapted,world,checkpoint,recall,send=forbidden_send,fetch=fetch)
        assert json.loads(recall.read_text())["entries"]==expected
        os.environ["LIVE_INFINITA_PAIRED_PHASE"]="repaired"
        repaired,repaired_log=native.godot(project,fixture,state,recall)
        client.close()
        def arm(result,name):return next(r for r in result["runs"] if r["arm"]==name)
        pairs=[]
        for i in range(2):
            b=arm(comparison,"stable_perception_"+str(i));c=arm(comparison,"stable_core_"+str(i))
            assert c["status"]["core_changed_initial_decisions"]==1
            assert c["recommendation"]["observation_ids"]
            pairs.append({"baseline":b,"recovered_core":c,"distance_delta_m":c["distance_m"]-b["distance_m"],
                "simulated_time_delta_s":c["simulated_seconds"]-b["simulated_seconds"]})
        assert abs(pairs[0]["distance_delta_m"]-pairs[1]["distance_delta_m"])<0.01
        assert pairs[0]["simulated_time_delta_s"]==pairs[1]["simulated_time_delta_s"]
        base=arm(comparison,"changed_perception");stale=arm(comparison,"changed_stale_core")
        fixed=arm(repaired,"changed_repaired_core")
        acquisition=training["runs"]+comparison["runs"][:4]+comparison["runs"][10:]
        assert len(comparison["runs"][10:-1])==12
        result={"schema":"live-infinita-paired-adaptation/v1","sdk_commit":native.SDK_COMMIT,
            "scope":"isolated_actual_capsule_and_native_collector","production_performance_advantage_demonstrated":False,
            "same_start_goal_physics_within_each_pair":True,"deterministic_repeats_not_independent_samples":True,
            "speed_mps":4,"dt_seconds":0.1,"training":training,"stable_pairs":pairs,
            "changed_perception":base,"changed_stale_core":stale,"adaptation_trials":comparison["runs"][10:-1],
            "changed_repaired_ram":arm(comparison,"changed_repaired_ram"),"changed_repaired_core":fixed,
            "changed_stale_minus_baseline_distance_m":stale["distance_m"]-base["distance_m"],
            "repaired_minus_stale_distance_m":fixed["distance_m"]-stale["distance_m"],
            "repaired_minus_baseline_distance_m":fixed["distance_m"]-base["distance_m"],
            "intake":intake,"cold_recovery":recovered,"adapted_intake":batches,
            "adapted_cold_recovery":repaired_recovery,"stored_physical_outcomes":4+len(rows),"adapted_fixture_outcomes":len(rows),
            "acquisition_traversals":len(acquisition),
            "acquisition_distance_m":sum(r["distance_m"] for r in acquisition),
            "acquisition_simulated_seconds":sum(r["simulated_seconds"] for r in acquisition),
            "adapted_ram_verification_added_one_physical_outcome":True,
            "training_and_adaptation_cost_included_in_claim":False,
            "limit":"Held-out traversal savings exclude acquisition cost. Exact sensor signatures can alias changed geometry; this is one synthetic physical fixture, not a live counterfactual or broad generalization."}
        return result,training_log,comparison_log,repaired_log
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True);a=p.parse_args()
    result,*logs=run(a.project);a.output_dir.mkdir(parents=True,exist_ok=True)
    (a.output_dir/"PAIRED_ADAPTATION_008EN.json").write_text(json.dumps(result,indent=2)+"\n")
    for name,log in zip(("TRAINING","COMPARISON","REPAIRED"),logs):
        (a.output_dir/(name+"_008EN.txt")).write_text(log)
    print(json.dumps({"pairs":[{"distance_delta_m":x["distance_delta_m"],"time_delta_s":x["simulated_time_delta_s"]} for x in result["stable_pairs"]],
        "stale_penalty_m":result["changed_stale_minus_baseline_distance_m"],
        "repair_delta_m":result["repaired_minus_stale_distance_m"],"stored":result["stored_physical_outcomes"]}))
if __name__=="__main__":main()
