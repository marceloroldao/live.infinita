#!/usr/bin/env python3
"""Native motion -> sealed collector file -> production bridge -> reopened isolated core."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from nov_animal_approach_context import payload,recover,recommend,NATIVE_PROFILE
from nov_spatial_memory_sync import _validate_ack
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-context-008ff"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);runs=[];cold_reports=[]
    with tempfile.TemporaryDirectory(prefix="008fg-native-context-") as folder:
        tmp=pathlib.Path(folder);world,checkpoint,recall=[tmp/n for n in ("world","checkpoint","recall")]
        world.write_text(json.dumps({"world_id":WORLD}));key="isolated-native-context-"+("x"*32)
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
        # Actual direct-motion observations from 008FF, retained with their distinct profile.
        old=json.loads((ROOT/"docs/APPROACH_CONTEXT_008FF/hidden_report.json").read_text())["persisted_outcomes"][:4]
        for value in old:
            request=payload(value);receipt=send(request);_validate_ack(receipt,request)
            assert receipt["stored"] and receipt["backend"]=="sqlite"
        old_recovered=recover(fetch(),WORLD)
        assert len(old_recovered)==4
        for i,(hidden,reverse,target) in enumerate((h,r,t) for h in (False,True) for r in (False,True) for t in ("perception",WORLD+":rabbit:1")):
            label=("hidden" if hidden else "visible")+("_changed" if reverse else "_initial")+("_near" if target=="perception" else "_far")
            state=tmp/label;source=pathlib.Path(str(state)+".context")
            clock=300000+i*100000
            env=dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_HIDDEN="1" if hidden else "0",
                LIVE_INFINITA_APPROACH_TEST_REVERSE="1" if reverse else "0",XDG_DATA_HOME=str(tmp/"userdata"))
            p=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_full_motion_008fg.gd")],
                env=env,capture_output=True,text=True,timeout=60)
            log=p.stdout+p.stderr;(out/(label+".log")).write_text(log)
            assert p.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
            values=[json.loads(l.split(" ",1)[1]) for l in p.stdout.splitlines() if l.startswith("008FG_PHYSICAL ")]
            assert len(values)==1
            d=values[0]
            assert d["fact"]["result"]=="approached" and d["contacts"]==0 and d["route_plan_builds"]==0
            assert d["context_fact"]["context"]["profile"]==NATIVE_PROFILE
            rejection=recommend(d["candidates"],old_recovered,WORLD,clock)
            assert rejection["source"]=="perception" and rejection["entity_id"]==WORLD+":rabbit:0"
            bridged=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
            assert bridged["acked_this_poll"]==1 and bridged["cached_recovered"]==i+1 and service.store.count==i+5
            (out/(label+"_source.json")).write_bytes(source.read_bytes())
            d.update(bridge=bridged,old_direct_profile_rejected=rejection)
            (out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n");runs.append(d)
            if i in (3,7):
                expected=json.loads(recall.read_text())["entries"]
                client.close();client=None;service=None;service,client=connect();recall.unlink()
                def forbidden(_):raise AssertionError("Cold recovery must not reingest")
                cold=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
                assert cold["acked_this_poll"]==0 and json.loads(recall.read_text())["entries"]==expected and service.store.count==i+5
                cold_reports.append(cold)
        client.close()
        report={"schema":"live-infinita-native-approach-context-validation/v1","sdk_commit":SDK_COMMIT,"actual_native_traversals":8,"native_facts_stored":8,
            "prior_actual_direct_facts_retained":4,"cold_recoveries":cold_reports,"runs":runs,"production_changed":False,
            "target_decision_changed_in_production":False,"production_benefit_demonstrated":False,
            "limits":["Actual local motion, anticipation and contour on flat terrain; full presentation, terrain streaming and fleeing prey not exercised.",
                      "All eight attempts conclude: direct-motion failure advantage from 008FF does not transfer to these native navigation cases.",
                      "Speed fixed at 4 m/s in fixture; live uses acceleration and variable speed.",
                      "Contexts are coarse; collection integration only. Native selector remains nearest visible target."]}
        (out/"NATIVE_CONTEXT_VALIDATION_008FG.json").write_text(json.dumps(report,indent=2)+"\n")
        print("008FG_NATIVE_CONTEXT_CORE_PASS traversals=8 native_facts=8 old_direct_retained=4 cold_recoveries=2")
if __name__=="__main__":main()
