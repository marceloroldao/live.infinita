#!/usr/bin/env python3
"""Repeated changes with production baseline, fixed epoch, and renewable epoch."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
SCRIPT=native.ROOT/"tests/godot_repeated_changes_008eq.gd"
def godot(project,fixture,state,policy,recall=None):
    env=dict(os.environ,LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),
        LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state),LIVE_INFINITA_REPEATED_POLICY=policy,
        LIVE_INFINITA_NAVIGATION_COST_SHIFT="1" if policy=="integrated" else "0",
        LIVE_INFINITA_EXPERIMENTAL_POLICY_PATH=str(native.ROOT/"tests/godot_cost_shift_policy_008eq.gd")
            if policy=="renewable_epoch" else "")
    env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL",None)
    if recall:env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"]=str(recall)
    p=subprocess.run([native.ENGINE,"--headless","--audio-driver","Dummy","--path",str(project),
        "--script",str(SCRIPT),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=240)
    log=p.stdout+p.stderr
    if p.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):
        raise RuntimeError(log[-6000:])
    results=[json.loads(l.split(" ",1)[1]) for l in p.stdout.splitlines()
        if l.startswith("008EH_NATIVE_PATTERN_COMPARISON ")]
    assert len(results)==1 and results[0]["failures"]==0
    return results[0],log
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008en-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True);summaries=[]
    for policy in ("integrated",):
        with tempfile.TemporaryDirectory(prefix="008eq-"+policy+"-") as raw:
            tmp=pathlib.Path(raw);fixture=tmp/"fixture.json";state=tmp/"state.json"
            result,log=godot(a.project,fixture,state,policy)
            (a.output_dir/(policy+".json")).write_text(json.dumps(result,indent=2)+"\n")
            (a.output_dir/(policy+".txt")).write_text(log)
            facts=json.loads(fixture.read_text())
            (a.output_dir/(policy+"_facts.json")).write_text(json.dumps(facts,indent=2)+"\n")
            phases=[]
            for phase in result["phases"]:
                base=phase["perception"];trials=phase["trials"]
                phases.append({"opening_z":phase["opening_z"],"distance_m":sum(r["distance_m"] for r in trials),
                    "simulated_seconds":sum(r["simulated_seconds"] for r in trials),
                    "distance_delta_vs_perception_m":sum(r["distance_m"]-base["distance_m"] for r in trials),
                    "sides":[r["side"] for r in trials],
                    "sources":[r["recommendation"].get("source","") for r in trials],
                    "last_distance_m":trials[-1]["distance_m"],
                    "collisions":sum(r["collisions"] for r in trials),"rescues":sum(int(r["rescued"]) for r in trials)})
            summary={"policy":policy,"phases":phases,"physical_outcomes":len(facts["rows"])}
            summaries.append(summary);print(json.dumps(summary),flush=True)
            if policy=="integrated":
                sys.path.insert(0,str(native.SDK))
                from fastapi import FastAPI
                from fastapi.testclient import TestClient
                from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
                key="isolated-repeated-"+("x"*32)
                def connect():
                    service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
                    app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
                    return service,TestClient(app)
                service,client=connect()
                def send(row):
                    response=client.post("/api/v1/structural/observations?defer_associations=true",json=row,headers={"X-Memoria-Key":key})
                    assert response.status_code==201,response.text
                    return response.json()
                def fetch():
                    response=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
                    assert response.status_code==200,response.text
                    return response.json()
                world=tmp/"world.json";world.write_text(json.dumps({"world_id":"native-pattern-008eh"}))
                checkpoint=tmp/"checkpoint.json";recall=tmp/"recall.json";batches=[]
                for _ in range(20):
                    batch=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch);batches.append(batch)
                    if batch["acked"]==0:break
                assert service.store.count==len(facts["rows"])<=64
                expected=json.loads(recall.read_text())["entries"];client.close();del service
                service,client=connect();recall.unlink()
                def forbidden(_):raise AssertionError("Reopen must not reingest")
                recovered=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
                assert recovered["acked"]==0 and json.loads(recall.read_text())["entries"]==expected
                cold,cold_log=godot(a.project,fixture,state,policy,recall);client.close()
                summary["core"]={"intake":batches,"recovered":recovered,"cold":cold,"sdk_commit":native.SDK_COMMIT}
                (a.output_dir/"COLD_CORE.txt").write_text(cold_log)
    output={"schema":"live-infinita-integrated-cost-windows/v1","planned_openings":[-20,-110,0,-20],
        "trials_per_phase":12,"policies":summaries,"production_policy_changed":False,
        "scope":"isolated_actual_native_physics; repeated related flat-wall changes"}
    (a.output_dir/"INTEGRATED_COST_WINDOWS_008ER.json").write_text(json.dumps(output,indent=2)+"\n")
if __name__=="__main__":main()
