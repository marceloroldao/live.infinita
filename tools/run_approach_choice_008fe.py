#!/usr/bin/env python3
"""Isolated paired physical target choices and a changed-obstacle counterexample."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from hashlib import sha256
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_approach_sync import SCHEMA,sync_once
from nov_animal_approach_candidate import recommend
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-choice-008fe"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True)
    def physical(label,target="",reverse=False,clock=100000):
        env=dict(os.environ,LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),LIVE_INFINITA_APPROACH_TEST_TARGET=target,
                 LIVE_INFINITA_APPROACH_TEST_REVERSE="1" if reverse else "0")
        run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_choice_008fe.gd")],
                           env=env,capture_output=True,text=True,timeout=60)
        log=run.stdout+run.stderr;(out/(label+".log")).write_text(log)
        assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
        values=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FE_PHYSICAL ")]
        assert len(values)==1
        (out/(label+".json")).write_text(json.dumps(values[0],indent=2)+"\n")
        return values[0]
    candidates=physical("probe")["candidates"]
    ids=[r["entity_id"] for r in sorted(candidates,key=lambda c:c["distance_m"])]
    with tempfile.TemporaryDirectory(prefix="008fe-physical-choice-") as folder:
        tmp=pathlib.Path(folder);source,world,checkpoint,recall=[tmp/n for n in ("source","world","checkpoint","recall")]
        world.write_text(json.dumps({"world_id":WORLD}));rows=[];recoveries=[]
        key="isolated-choice-"+("x"*32)
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
        def store():
            raw=json.dumps({"schema":SCHEMA,"records":rows,"pending":{}})
            source.write_text(json.dumps({"payload":raw,"sha256":sha256(raw.encode()).hexdigest()}))
            d=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
            assert d["acked_this_poll"]==1 and d["cached_recovered"]==len(rows)
        def cold():
            nonlocal service,client
            expected=json.loads(recall.read_text())["entries"]
            client.close();client=None;service=None;service,client=connect();recall.unlink()
            def forbidden(_):raise AssertionError("Cold retrieval may not reingest")
            d=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
            assert d["acked_this_poll"]==0 and service.store.count==len(rows) and json.loads(recall.read_text())["entries"]==expected
            recoveries.append(d);return expected
        # Balanced acquisition is an experiment schedule, not a learned online exploration policy.
        for i in range(4):
            d=physical("acquisition_"+str(i),ids[i%2],False,100000+i*20000)
            assert d["fact"]["result"]==("no_progress" if i%2==0 else "approached")
            rows.append(d["fact"]);store()
        known=cold()
        def pair(label,reverse,clock,entries):
            decision=recommend(candidates,entries,WORLD,clock)
            baseline=physical(label+"_perception","perception",reverse,clock)
            memory=physical(label+"_memory",decision["entity_id"],reverse,clock)
            assert baseline["fact"]["entity_id"]==ids[0]
            assert baseline["candidates"]==memory["candidates"]==candidates
            value={"phase":label,"decision":decision,"perception":baseline,"memory":memory}
            (out/(label+"_pair.json")).write_text(json.dumps(value,indent=2)+"\n")
            return value
        stable=pair("stable",False,200000,known)
        assert stable["decision"]["source"]=="recovered-approach-evidence"
        assert stable["perception"]["fact"]["result"]=="no_progress" and stable["memory"]["fact"]["result"]=="approached"
        changed=pair("changed_without_new_experience",True,220000,known)
        assert changed["perception"]["fact"]["result"]=="approached" and changed["memory"]["fact"]["result"]=="no_progress"
        for i in range(4):
            d=physical("changed_acquisition_"+str(i),ids[i%2],True,240000+i*20000)
            assert d["fact"]["result"]==("approached" if i%2==0 else "no_progress")
            rows.append(d["fact"]);store()
        updated=cold()
        adapted=pair("changed_after_new_experience",True,340000,updated)
        assert adapted["decision"]["entity_id"]==ids[0] and adapted["memory"]["fact"]["result"]=="approached"
        client.close()
        report={"schema":"live-infinita-approach-choice-experiment/v1","sdk_commit":SDK_COMMIT,"backend":"sqlite","allow_fallback":False,
                "actual_traversals":14,"persisted_actual_outcomes":8,"cold_recoveries":recoveries,"pairs":[stable,changed,adapted],
                "production_changed":False,"production_benefit_demonstrated":False,"capture":False,
                "limits":["Constructed direct-approach fixture; full native contour navigation is not exercised.",
                          "Two fixed visible rabbits with different initial distance buckets; low static fences, no prey fleeing.",
                          "Balanced acquisition is externally scheduled, not autonomous learned exploration.",
                          "Distance alone is a coarse context; stale history caused a measured worse decision after obstacle reversal.",
                          "Newest two outcomes per bucket adapt only after fresh balanced experience; no universal guarantee.",
                          "20-point failure penalty and 20% preference margin are hand-set experimental policy constants."]}
        (out/"APPROACH_CHOICE_008FE.json").write_text(json.dumps(report,indent=2)+"\n")
        (out/"persisted_physical_outcomes.json").write_text(json.dumps(rows,indent=2)+"\n")
        print("008FE_PHYSICAL_CHOICE_PASS traversals=14 facts=8 cold_recoveries=2 stale_memory_counterexample=1")
if __name__=="__main__":main()
