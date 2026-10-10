#!/usr/bin/env python3
"""Physical context change, perception-only control, and cold failure-driven re-exploration."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_approach_context import payload,recover,recommend
from nov_spatial_memory_sync import _validate_ack,_observation_id
from nov_animal_approach_sync import payload as base_payload
from nov_animal_approach_candidate import recommend as distance_only
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-context-008ff"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);traversals=0;cases=[]
    def physical(label,target="",reverse=False,hidden=False,clock=100000):
        nonlocal traversals
        env=dict(os.environ,LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),LIVE_INFINITA_APPROACH_TEST_TARGET=target,
                 LIVE_INFINITA_APPROACH_TEST_REVERSE="1" if reverse else "0",LIVE_INFINITA_APPROACH_TEST_HIDDEN="1" if hidden else "0")
        run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_context_008ff.gd")],env=env,capture_output=True,text=True,timeout=60)
        log=run.stdout+run.stderr;(out/(label+".log")).write_text(log)
        assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
        values=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FF_PHYSICAL ")]
        assert len(values)==1
        d=values[0];(out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n")
        traversals+=not d["probe"]
        return d
    with tempfile.TemporaryDirectory(prefix="008ff-context-core-") as folder:
        tmp=pathlib.Path(folder)
        for hidden in (False,True):
            name="hidden" if hidden else "visible";rows=[];cold_count=0
            key="isolated-context-"+("x"*32)
            def connect():
                service=ProductStructuralObservationService.open(tmp/name,backend="sqlite",allow_fallback=False)
                app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
                return service,TestClient(app)
            service,client=connect()
            def cold():
                nonlocal service,client,cold_count
                client.close();client=None;service=None;service,client=connect();cold_count+=1
                response=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
                assert response.status_code==200,response.text
                entries=recover(response.json(),WORLD)
                assert len(entries)==service.store.count==len(rows)
                # Recovered content must exactly equal actual fixture measurements.
                expected=sorted(rows,key=lambda r:r["approach"]["id"])
                actual=sorted([{k:v for k,v in e.items() if k!="observation_id"} for e in entries],key=lambda r:r["approach"]["id"])
                assert expected==actual
                return entries
            def store(d):
                value=d["context_fact"];request=payload(value)
                response=client.post("/api/v1/structural/observations?defer_associations=true",json=request,headers={"X-Memoria-Key":key})
                assert response.status_code==201,response.text
                receipt=response.json();_validate_ack(receipt,request)
                assert receipt["stored"] and not receipt["duplicate"] and receipt["backend"]=="sqlite"
                rows.append(value)
                return cold()
            initial=physical(name+"_probe",hidden=hidden)["candidates"]
            ids=[c["entity_id"] for c in sorted(initial,key=lambda c:c["distance_m"])]
            assert [c["context"]["blocked_ahead"] for c in sorted(initial,key=lambda c:c["distance_m"])]==([False,False] if hidden else [True,False])
            for i in range(4):
                d=physical(name+"_acquisition_"+str(i),ids[i%2],hidden=hidden,clock=100000+i*20000)
                assert d["fact"]["result"]==("no_progress" if i%2==0 else "approached")
                known=store(d)
            probe=physical(name+"_stable_probe",hidden=hidden,clock=200000)["candidates"]
            decision=recommend(probe,known,WORLD,200000)
            assert decision["entity_id"]==ids[1] and decision["source"]=="recovered-contextual-evidence"
            baseline=physical(name+"_stable_perception","perception",hidden=hidden,clock=200000)
            memory=physical(name+"_stable_contextual",decision["entity_id"],hidden=hidden,clock=200000)
            assert baseline["candidates"]==memory["candidates"]==probe
            assert baseline["fact"]["result"]=="no_progress" and memory["fact"]["result"]=="approached"
            record={"case":name,"stable":{"decision":decision,"perception":baseline,"contextual":memory}}
            if not hidden:
                clear_choice=min(probe,key=lambda c:(c["context"]["blocked_ahead"],c["distance_m"]))["entity_id"]
                physics=physical(name+"_stable_physics_only",clear_choice,clock=200000)
                assert physics["fact"]["result"]=="approached"
                current=physical(name+"_changed_probe",reverse=True,clock=220000)["candidates"]
                adapted=recommend(current,known,WORLD,220000)
                legacy=distance_only([{k:c[k] for k in ("entity_id","distance_m")} for c in current],
                    [dict(e["approach"],observation_id=_observation_id(base_payload(e["approach"])["event"])) for e in known],WORLD,220000)
                # Legacy selector here receives the same recovered base measurements via a test adapter.
                assert legacy["entity_id"]==ids[1] and adapted["entity_id"]==ids[0]
                bad=physical(name+"_changed_distance_only",legacy["entity_id"],reverse=True,clock=220000)
                good=physical(name+"_changed_contextual",adapted["entity_id"],reverse=True,clock=220000)
                physics_changed=physical(name+"_changed_physics_only",min(current,key=lambda c:(c["context"]["blocked_ahead"],c["distance_m"]))["entity_id"],reverse=True,clock=220000)
                assert bad["fact"]["result"]=="no_progress" and good["fact"]["result"]==physics_changed["fact"]["result"]=="approached"
                record.update(physics_only=physics,changed={"legacy":bad,"contextual":good,"decision":adapted,"physics_only":physics_changed})
            else:
                current=physical(name+"_changed_probe",reverse=True,hidden=True,clock=220000)["candidates"]
                assert all(not c["context"]["blocked_ahead"] for c in current)
                stale=recommend(current,known,WORLD,220000)
                failed=physical(name+"_changed_first_failure",stale["entity_id"],reverse=True,hidden=True,clock=220000)
                assert failed["fact"]["result"]=="no_progress";known=store(failed)
                probes=[]
                for i in range(3):
                    clock=240000+i*20000
                    current=physical(name+"_reassessment_probe_"+str(i),reverse=True,hidden=True,clock=clock)["candidates"]
                    choice=recommend(current,known,WORLD,clock)
                    assert choice["source"]=="recovered-failure-reassessment"
                    d=physical(name+"_autonomous_reassessment_"+str(i),choice["entity_id"],reverse=True,hidden=True,clock=clock)
                    probes.append({"decision":choice,"attempt":d});known=store(d)
                assert [p["decision"]["entity_id"] for p in probes]==[ids[0],ids[1],ids[0]]
                current=physical(name+"_final_probe",reverse=True,hidden=True,clock=320000)["candidates"]
                final=recommend(current,known,WORLD,320000)
                assert final["entity_id"]==ids[0]
                good=physical(name+"_final_contextual",final["entity_id"],reverse=True,hidden=True,clock=320000)
                control=physical(name+"_final_perception","perception",reverse=True,hidden=True,clock=320000)
                assert good["fact"]["result"]==control["fact"]["result"]=="approached"
                record.update(changed_first_failure=failed,reassessment=probes,final={"decision":final,"contextual":good,"perception":control})
            record.update(persisted_outcomes=rows,cold_recoveries=cold_count)
            client.close();cases.append(record);(out/(name+"_report.json")).write_text(json.dumps(record,indent=2)+"\n")
    assert traversals==22
    report={"schema":"live-infinita-context-reassessment-experiment/v1","sdk_commit":SDK_COMMIT,"traversals":traversals,"persisted_actual_facts":12,
            "cold_recoveries":sum(c["cold_recoveries"] for c in cases),"cases":cases,"production_changed":False,"production_benefit_demonstrated":False,
            "limits":["Direct collision approach fixture, no full contour navigation or moving prey.",
                      "Initial balanced acquisition is scheduled; only reassessment choices are autonomously derived from recovered failures.",
                      "Four-metre physics sweep is explicit perception; visible-obstacle physics-only control matches contextual outcomes.",
                      "Hidden change still causes one first failure and three probes; adaptation does not foresee unobserved obstacles.",
                      "Coarse context and hand-set sample/score rules; deterministic two-target family only."]}
    (out/"APPROACH_CONTEXT_008FF.json").write_text(json.dumps(report,indent=2)+"\n")
    print("008FF_CONTEXT_REASSESSMENT_PASS traversals=22 facts=12 cold_recoveries=12")
if __name__=="__main__":main()
