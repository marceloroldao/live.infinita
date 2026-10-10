#!/usr/bin/env python3
"""Native bounded approach, production collector/bridge, cold core, paired controls."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from nov_animal_approach_context import recommend
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-native-failure-008fh"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="008fh-native-failure-") as folder:
        tmp=pathlib.Path(folder);world,checkpoint,recall=[tmp/n for n in ("world","checkpoint","recall")]
        world.write_text(json.dumps({"world_id":WORLD}));key="isolated-native-failure-"+("x"*32)
        traversals=0;rows=[];cold_reports=[];runs=[]
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
        def physical(label,target="",reverse=False,clock=100000):
            nonlocal traversals
            state=tmp/label
            env=dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_REVERSE="1" if reverse else "0",XDG_DATA_HOME=str(tmp/"userdata"))
            run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_native_failure_008fh.gd")],
                env=env,capture_output=True,text=True,timeout=60)
            log=run.stdout+run.stderr;(out/(label+".log")).write_text(log)
            assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
            values=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FH_PHYSICAL ")]
            assert len(values)==1
            d=values[0];d["label"]=label
            if not d["probe"]:
                assert d["route_plan_builds"]==0 and d["contacts"]==0
                traversals+=1;runs.append(d)
                source=pathlib.Path(str(state)+".context")
                sealed=json.loads(source.read_text());actual=json.loads(sealed["payload"])["records"]
                assert len(actual)==1 and actual[0]==d["context_fact"]
                (out/(label+"_source.json")).write_bytes(source.read_bytes())
            (out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n")
            return d,pathlib.Path(str(state)+".context")
        def store_and_cold(d,source):
            nonlocal service,client
            report=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
            assert report["acked_this_poll"]==1
            rows.append(d["context_fact"])
            before=json.loads(recall.read_text())["entries"]
            client.close();client=None;service=None;service,client=connect();recall.unlink()
            def forbidden(_):raise AssertionError("Cold retrieval must not POST")
            cold=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
            after=json.loads(recall.read_text())["entries"]
            assert cold["acked_this_poll"]==0 and after==before and service.store.count==len(rows)==cold["cached_recovered"]
            expected=sorted(rows,key=lambda r:r["approach"]["id"])
            actual=sorted([{k:v for k,v in e.items() if k!="observation_id"} for e in after],key=lambda r:r["approach"]["id"])
            assert actual==expected
            cold_reports.append(cold);return after
        probe,_=physical("initial_probe")
        ids=[c["entity_id"] for c in sorted(probe["candidates"],key=lambda c:c["distance_m"])]
        assert all(not c["context"]["blocked_ahead"] for c in probe["candidates"])
        acquisition=[]
        for i in range(4):
            d,source=physical("acquisition_"+str(i),ids[i%2],clock=100000+i*30000)
            assert d["fact"]["result"]==("contact_lost" if i%2==0 else "approached")
            known=store_and_cold(d,source);acquisition.append(d)
        stable,_=physical("stable_probe",clock=240000)
        decision=recommend(stable["candidates"],known,WORLD,240000)
        empty=recommend(stable["candidates"],[],WORLD,240000)
        assert decision["entity_id"]==ids[1] and decision["source"]=="recovered-contextual-evidence"
        assert empty["entity_id"]==ids[0] and empty["source"]=="perception"
        baseline,_=physical("stable_perception","perception",clock=240000)
        memory,_=physical("stable_memory",decision["entity_id"],clock=240000)
        assert stable["candidates"]==baseline["candidates"]==memory["candidates"]
        assert baseline["fact"]["result"]=="contact_lost" and memory["fact"]["result"]=="approached"
        changed,_=physical("changed_probe",reverse=True,clock=270000)
        assert all(not c["context"]["blocked_ahead"] for c in changed["candidates"])
        stale=recommend(changed["candidates"],known,WORLD,270000)
        assert stale["entity_id"]==ids[1]
        failed,source=physical("changed_first_failure",stale["entity_id"],reverse=True,clock=270000)
        assert failed["fact"]["result"]=="contact_lost"
        known=store_and_cold(failed,source);probes=[]
        for i in range(3):
            clock=300000+i*30000
            current,_=physical("reassessment_probe_"+str(i),reverse=True,clock=clock)
            choice=recommend(current["candidates"],known,WORLD,clock)
            assert choice["source"]=="recovered-failure-reassessment"
            d,source=physical("autonomous_reassessment_"+str(i),choice["entity_id"],reverse=True,clock=clock)
            assert d["candidates"]==current["candidates"]
            known=store_and_cold(d,source);probes.append({"decision":choice,"attempt":d})
        assert [p["decision"]["entity_id"] for p in probes]==[ids[0],ids[1],ids[0]]
        final_probe,_=physical("final_probe",reverse=True,clock=420000)
        final=recommend(final_probe["candidates"],known,WORLD,420000)
        assert final["entity_id"]==ids[0] and final["source"]=="perception"
        good,_=physical("final_memory",final["entity_id"],reverse=True,clock=420000)
        control,_=physical("final_perception","perception",reverse=True,clock=420000)
        assert good["fact"]["result"]==control["fact"]["result"]=="approached"
        assert good["candidates"]==control["candidates"]==final_probe["candidates"]
        assert traversals==12 and len(rows)==len(cold_reports)==8
        report={"schema":"live-infinita-native-failure-reassessment/v1","sdk_commit":SDK_COMMIT,
            "actual_native_traversals":traversals,"facts_confirmed_and_cold_recovered":len(rows),"cold_recoveries":cold_reports,
            "acquisition":acquisition,"stable":{"decision":decision,"empty_memory_ablation":empty,"perception":baseline,"memory":memory},
            "changed":{"stale_decision":stale,"first_failure":failed,"autonomous_reassessment":probes},
            "final":{"decision":final,"memory":good,"perception":control},"persisted_actual_facts":rows,
            "production_changed":False,"production_benefit_demonstrated":False,
            "limits":["Flat terrain, fixed 4 m/s speed and stationary rabbits; no live scene or escaping prey.",
                "Eyes follow the last observed target point during approach; this is a controlled sensor-attention fixture, not the live camera.",
                "Long low fence causes loss of physical sight after detour increases range beyond the sensor; no collision or obstacle-coordinate penalty is injected.",
                "Initial four attempts use a scheduled balanced acquisition; only three reassessment probes are autonomously chosen from recovered facts.",
                "Coarse context buckets and existing explicit sample/score rules; one deterministic two-target family.",
                "Stable paired comparison has different target and measured outcome; after reversal the final choice equals perception and is not an additional gain."]}
        (out/"NATIVE_FAILURE_REASSESSMENT_008FH.json").write_text(json.dumps(report,indent=2)+"\n")
        client.close()
        print("008FH_NATIVE_FAILURE_REASSESSMENT_PASS traversals=12 actual_facts=8 cold_recoveries=8 autonomous_probes=3")
if __name__=="__main__":main()
