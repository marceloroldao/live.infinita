#!/usr/bin/env python3
"""Current-policy paired physical evaluation, including observed acquisition cost."""
import argparse,json,math,os,pathlib,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
native.SCRIPT=native.ROOT/"tests/godot_acquisition_cost_008ev.gd"

def run(project,out):
    out.mkdir(parents=True,exist_ok=True)
    for flag in ("COST_SHIFT","CONTACT_TURNS","EXIT_DIRECTION"):
        os.environ["LIVE_INFINITA_NAVIGATION_"+flag]="1"
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008ev-cost-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall=[tmp/n for n in ("fixture.json","state.json","world.json","checkpoint.json","recall.json")]
        world.write_text(json.dumps({"world_id":"native-pattern-008eh"}))
        os.environ["LIVE_INFINITA_ACQUISITION_PHASE"]="training"
        training,log=native.godot(project,fixture,state)
        (out/"TRAINING_008EV.txt").write_text(log)
        facts=json.loads(fixture.read_text())
        assert len(facts["rows"])==4
        (out/"PHYSICAL_TRAINING_FACTS_008EV.json").write_text(json.dumps(facts,indent=2)+"\n")
        key="isolated-cost-"+("x"*32)
        def connect():
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            return service,TestClient(app)
        service,client=connect()
        def send(row):
            r=client.post("/api/v1/structural/observations?defer_associations=true",json=row,headers={"X-Memoria-Key":key})
            assert r.status_code==201,r.text
            return r.json()
        def fetch():
            r=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert r.status_code==200,r.text
            return r.json()
        intake=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch)
        expected=json.loads(recall.read_text())["entries"]
        assert intake["acked"]==4 and service.store.count==4
        client.close();del service
        service,client=connect();recall.unlink()
        def forbidden(_):raise AssertionError("Reopened recovery cannot reingest")
        recovery=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
        assert recovery["acked"]==0 and recovery["cached_recovered"]==4
        assert json.loads(recall.read_text())["entries"]==expected and service.store.count==4
        (out/"RECOVERED_ENTRIES_008EV.json").write_text(json.dumps(expected,indent=2)+"\n")
        client.close();del service
        os.environ["LIVE_INFINITA_ACQUISITION_PHASE"]="comparison"
        comparison,log=native.godot(project,fixture,state,recall)
        (out/"COMPARISON_008EV.txt").write_text(log)
        for data in (training,comparison):
            for row in data["runs"]:
                assert all(row["status"][key] for key in ("cost_shift_enabled","exit_direction_enabled","local_turn_continuity_enabled"))
                assert row["arrived"] and row["collisions"]==0 and not row["rescued"] and row["route_plan_builds"]==0
        def arm(data,label):return next(r for r in data["runs"] if r["arm"]==label)
        pairs=[]
        for scenario,n in (("stable",10),("changed",1)):
            for i in range(n):
                b=arm(comparison,scenario+"_perception_"+str(i));c=arm(comparison,scenario+"_core_"+str(i))
                assert c["recommendation"].get("source")=="recovered-pattern-evidence"
                assert c["recommendation"].get("observation_ids")
                assert c["status"]["core_changed_initial_decisions"]==1
                pairs.append({"scenario":scenario,"index":i,"perception":b,"core":c,
                    "saving_m":b["distance_m"]-c["distance_m"],
                    "saving_simulated_s":b["simulated_seconds"]-c["simulated_seconds"]})
        assert max(x["saving_m"] for x in pairs[:10])-min(x["saving_m"] for x in pairs[:10])<0.01
        mem=[r for r in training["runs"] if r["arm"].startswith("training_memory_")]
        base=[r for r in training["runs"] if r["arm"].startswith("training_perception_")]
        assert len(mem)==len(base)==4
        costs={}
        for metric,saving_key in (("distance_m","saving_m"),("simulated_seconds","saving_simulated_s")):
            total=sum(r[metric] for r in mem);control=sum(r[metric] for r in base)
            saving=pairs[0][saving_key];extra=total-control
            costs[metric]={"acquisition_total":total,"same_four_tasks_perception":control,
                "acquisition_extra":extra,"saving_per_stable_reuse":saving,
                "full_cost_break_even_reuses":math.ceil(max(0,total)/saving) if saving>0 else None,
                "incremental_break_even_reuses":math.ceil(max(0,extra)/saving) if saving>0 else None,
                "observed_ten_reuses_net_after_full_acquisition":sum(p[saving_key] for p in pairs[:10])-total,
                "observed_ten_reuses_net_after_extra_acquisition":sum(p[saving_key] for p in pairs[:10])-extra}
        result={"schema":"live-infinita-acquisition-cost/v1","sdk_commit":native.SDK_COMMIT,
            "flags_identical_in_both_arms":{"cost_shift":True,"contact_turns":True,"exit_direction":True},
            "training":training,"pairs":pairs,"cost_accounting":costs,"intake":intake,"cold_recovery":recovery,
            "stored_real_physical_facts":4,"core_reopened_cache_deleted_no_reingest":True,
            "production_benefit_demonstrated":False,
            "limits":["One flat physical wall fixture; exact sensor context can alias changed geometry.",
                "Ten deterministic reuses are not independent samples or production measurements.",
                "Comparison uses a fixed recovered snapshot; changed case measures stale evidence, not adaptation.",
                "Time is simulated movement time; SDK, CPU, storage and network costs are not included.",
                "Successful paths only in this fixture; physical error penalty is not exercised."]}
        (out/"ACQUISITION_COST_008EV.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"cost_accounting":costs,"changed_saving_m":pairs[-1]["saving_m"],"stored":4}))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True)
    a=p.parse_args();run(a.project,a.output_dir)
if __name__=="__main__":main()
