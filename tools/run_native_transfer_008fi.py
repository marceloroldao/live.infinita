#!/usr/bin/env python3
"""Held-out native transfer and coarse-context counterexample; no live changes."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from nov_animal_approach_context import recommend
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-native-transfer-008fi"
CASES=[
 {"name":"slow_new_animals","serial":20,"speed":2,"near":14,"far":21,"wall":6,"length":60,"expected":"gain"},
 {"name":"fast_new_animals","serial":40,"speed":6,"near":17,"far":23,"wall":6,"length":100,"expected":"gain"},
 {"name":"moved_hidden_barrier","serial":60,"speed":4,"near":15,"far":22,"wall":7,"length":70,"expected":"gain"},
 {"name":"thin_distance_variation","serial":80,"speed":4,"near":17.5,"far":20.5,"wall":5,"length":90,"expected":"gain"},
 {"name":"barrier_after_confirmation","serial":90,"speed":4,"near":16,"far":22,"wall":12.5,"length":80,"expected":"regression"},
]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="008fi-native-transfer-") as folder:
        tmp=pathlib.Path(folder);world,checkpoint,recall=[tmp/n for n in ("world","checkpoint","recall")]
        world.write_text(json.dumps({"world_id":WORLD}));key="isolated-native-transfer-"+("x"*32)
        traversals=0;rows=[];cold_reports=[]
        def connect():
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            return service,TestClient(app)
        service,client=connect()
        def send(request):
            r=client.post("/api/v1/structural/observations?defer_associations=true",json=request,headers={"X-Memoria-Key":key})
            assert r.status_code==201,r.text
            return r.json()
        def fetch():
            r=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert r.status_code==200,r.text
            return r.json()
        def cold(source):
            nonlocal service,client
            before=json.loads(recall.read_text())["entries"]
            client.close();client=None;service=None;service,client=connect();recall.unlink()
            def forbidden(_):raise AssertionError("Cold retrieval must not POST")
            d=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
            after=json.loads(recall.read_text())["entries"]
            assert d["acked_this_poll"]==0 and before==after and service.store.count==len(rows)==d["cached_recovered"]
            actual=sorted([{k:v for k,v in e.items() if k!="observation_id"} for e in after],key=lambda r:r["approach"]["id"])
            assert actual==sorted(rows,key=lambda r:r["approach"]["id"])
            cold_reports.append(d);return after
        def physical(label,target="",clock=100000,case=None):
            nonlocal traversals
            case=case or {"serial":0,"speed":4,"near":16,"far":22,"wall":6,"length":80}
            state=tmp/label
            env=dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_REVERSE="0",XDG_DATA_HOME=str(tmp/"userdata"))
            for suffix,keyname in [("SPEED","speed"),("NEAR","near"),("FAR","far"),("WALL_AT","wall"),("WALL_LENGTH","length"),("ANIMAL_SERIAL","serial")]:
                env["LIVE_INFINITA_TRANSFER_"+suffix]=str(case[keyname])
            run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_native_transfer_008fi.gd")],
                env=env,capture_output=True,text=True,timeout=60)
            log=run.stdout+run.stderr;(out/(label+".log")).write_text(log)
            assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
            values=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FI_PHYSICAL ")]
            assert len(values)==1
            d=values[0];d["label"]=label
            if not d["probe"]:
                assert d["route_plan_builds"]==0 and d["contacts"]==0
                traversals+=1
                source=pathlib.Path(str(state)+".context")
                sealed=json.loads(source.read_text());actual=json.loads(sealed["payload"])["records"]
                assert len(actual)==1 and actual[0]==d["context_fact"]
                (out/(label+"_source.json")).write_bytes(source.read_bytes())
            (out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n")
            return d,pathlib.Path(str(state)+".context")
        acquisition=[]
        for i in range(4):
            target=WORLD+":rabbit:"+str(i%2)
            d,source=physical("acquisition_"+str(i),target,clock=100000+i*30000)
            assert d["fact"]["result"]==("contact_lost" if i%2==0 else "approached")
            receipt=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
            assert receipt["acked_this_poll"]==1
            rows.append(d["context_fact"]);known=cold(source);acquisition.append(d)
        training_ids={r["approach"]["entity_id"] for r in rows};last_source=source
        results=[]
        for i,case in enumerate(CASES):
            clock=300000+i*50000;known=cold(last_source)
            probe,_=physical(case["name"]+"_probe",clock=clock,case=case)
            candidates=probe["candidates"]
            assert all(not c["context"]["blocked_ahead"] for c in candidates)
            assert training_ids.isdisjoint({c["entity_id"] for c in candidates})
            decision=recommend(candidates,known,WORLD,clock)
            ablation=recommend(candidates,[],WORLD,clock)
            assert decision==recommend(list(reversed(candidates)),known,WORLD,clock)
            assert decision["entity_id"]==WORLD+":rabbit:"+str(case["serial"]+1) and decision["source"]=="recovered-contextual-evidence"
            assert ablation["entity_id"]==WORLD+":rabbit:"+str(case["serial"]) and ablation["source"]=="perception"
            baseline,_=physical(case["name"]+"_perception","perception",clock,case)
            memory,_=physical(case["name"]+"_memory",decision["entity_id"],clock,case)
            assert candidates==baseline["candidates"]==memory["candidates"]
            assert baseline["fixture"]==memory["fixture"]==probe["fixture"]
            assert memory["fact"]["result"]=="approached"
            if case["expected"]=="gain":
                assert baseline["fact"]["result"]!="approached"
                classification="failure_avoided"
            else:
                assert baseline["fact"]["result"]=="approached" and memory["distance_m"]>baseline["distance_m"]
                classification="unnecessary_longer_approach"
            assert service.store.count==4 and len(json.loads(recall.read_text())["entries"])==4
            results.append({"case":case,"decision":decision,"empty_memory_ablation":ablation,"perception":baseline,"memory":memory,
                            "classification":classification,"test_outcomes_ingested":False})
            print("008FI_CASE",case["name"],classification,flush=True)
        assert traversals==14 and len(rows)==4 and len(cold_reports)==9
        assert sum(c["classification"]=="failure_avoided" for c in results)==4
        report={"schema":"live-infinita-native-transfer/v1","sdk_commit":SDK_COMMIT,"actual_native_traversals":traversals,
            "training_facts_confirmed_and_cold_recovered":4,"cold_recoveries":cold_reports,"acquisition":acquisition,
            "cases":results,"held_out_cases":5,"different_animal_identities":10,"failure_avoidance_cases":4,
            "longer_successful_choice_cases":1,"production_changed":False,"production_benefit_demonstrated":False,
            "limits":["Four scheduled training attempts; no autonomous initial acquisition.",
                "Five designed held-out pairs, not a randomized statistical estimate; expectations are specified in the runner before execution.",
                "New animal identities, speeds 2/4/6 m/s, distances within the same trained buckets and long low fences; no unseen bucket guarantee.",
                "Flat terrain, stationary animals and sensor attention to last observed point, not the full live camera.",
                "One coarse-context counterexample: later barrier leaves the nearest animal reachable, while memory still selects the farther animal.",
                "Held-out outcomes remain outside the core to prevent validation leakage; no online adaptation in these five pairs."]}
        (out/"NATIVE_TRANSFER_008FI.json").write_text(json.dumps(report,indent=2)+"\n");client.close()
        print("008FI_NATIVE_TRANSFER_PASS traversals=14 training_facts=4 cold_recoveries=9 gain_cases=4 regression_cases=1")
if __name__=="__main__":main()
