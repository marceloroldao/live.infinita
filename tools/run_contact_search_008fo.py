#!/usr/bin/env python3
"""Bounded last-observed-point search compared with ending on lost contact."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-contact-search-008fo"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);reports=[];traversals=0
    with tempfile.TemporaryDirectory(prefix="008fo-cost-refresh-") as folder:
        for name,occlusion_s in (("two_seconds",2.0),("three_seconds",3.0)):
            animal_speed=1.0
            wall=6.0
            tmp=pathlib.Path(folder)/name;tmp.mkdir()
            world,checkpoint,recall=[tmp/n for n in ("world","checkpoint","recall")]
            world.write_text(json.dumps({"world_id":WORLD}));key="isolated-cost-refresh-"+("x"*32)
            rows=[];cold_reports=[];case_out=out/name;case_out.mkdir(exist_ok=True)
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
            def physical(label,target,clock,serial=0,wall_at=6,occlusion=0.0,recovery=False):
                nonlocal traversals
                state=tmp/label
                env=dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                    LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_REVERSE="0",XDG_DATA_HOME=str(tmp/"userdata"),
                    LIVE_INFINITA_TRANSFER_ANIMAL_SERIAL=str(serial),LIVE_INFINITA_TRANSFER_WALL_AT=str(wall_at),
                    LIVE_INFINITA_TEST_CONTACT_SEARCH="1" if recovery else "0",LIVE_INFINITA_TEST_OCCLUSION_S=str(occlusion),LIVE_INFINITA_TEST_ANIMAL_SPEED=str(animal_speed),LIVE_INFINITA_TRANSFER_SPEED="4",LIVE_INFINITA_TRANSFER_NEAR="16",LIVE_INFINITA_TRANSFER_FAR="22",
                    LIVE_INFINITA_TRANSFER_WALL_LENGTH="80")
                run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_contact_search_008fo.gd")],
                    env=env,capture_output=True,text=True,timeout=60)
                log=run.stdout+run.stderr;(case_out/(label+".log")).write_text(log)
                assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
                vals=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FO_PHYSICAL ")]
                assert len(vals)==1
                d=vals[0]
                source=pathlib.Path(str(state)+".context")
                if not d["probe"]:
                    traversals+=1
                    assert d["route_plan_builds"]==0
                    actual=json.loads(json.loads(source.read_text())["payload"])["records"]
                    assert len(actual)==1 and actual[0]==d["context_fact"]
                    (case_out/(label+"_source.json")).write_bytes(source.read_bytes())
                (case_out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n")
                return d,source
            def store_and_cold(d,source):
                nonlocal service,client
                ack=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
                assert ack["acked_this_poll"]==1
                rows.append(d["context_fact"]);expected=json.loads(recall.read_text())["entries"]
                client.close();client=None;service=None;service,client=connect();recall.unlink()
                def forbidden(_):raise AssertionError("Cold retrieval must not POST")
                cold=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
                known=json.loads(recall.read_text())["entries"]
                assert cold["acked_this_poll"]==0 and expected==known and service.store.count==len(rows)==cold["cached_recovered"]
                actual=sorted([{k:v for k,v in e.items() if k!="observation_id"} for e in known],key=lambda r:r["approach"]["id"])
                assert actual==sorted(rows,key=lambda r:r["approach"]["id"])
                cold_reports.append(cold);return known
            pairs=[]
            for i in range(2):
                clock=200000+i*20000
                target=WORLD+":rabbit:21"
                adaptive,source=physical("search_"+str(i),target,clock,20,wall,occlusion_s,True)
                control,_=physical("control_"+str(i),target,clock,20,wall,occlusion_s,False)
                assert adaptive["candidates"]==control["candidates"] and adaptive["fixture"]==control["fixture"]
                assert adaptive["fact"]["result"]==control["fact"]["result"]=="contact_lost"
                assert adaptive["fact"]["distance_m"]==control["fact"]["distance_m"]
                assert control["contact_search_result"]=={}
                recovery=adaptive["contact_search_result"]
                assert recovery["result"]=="reacquired" and not recovery["approach_confirmed"] and not recovery["learning_eligible"]
                assert recovery["ended_ms"]-recovery["reacquired_observed_ms"]<=300
                assert recovery["ended_ms"]-recovery["started_ms"]<5000 and recovery["distance_m"]<12
                assert abs(adaptive["distance_m"]-adaptive["base_distance_m"]-recovery["distance_m"])<0.0001
                assert adaptive["future_position_given_to_controller"]==False
                known=store_and_cold(adaptive,source)
                pairs.append({"search":adaptive,"control":control,"control_outcome_ingested":False})
                print("008FO_PAIR",name,i,recovery["result"],flush=True)
            assert len(rows)==len(cold_reports)==2
            report={"case":name,"pairs":pairs,"persisted_actual_facts":rows,"cold_recoveries":cold_reports,
                "occlusion_s":occlusion_s,"reacquisitions":2,"control_reacquisitions":0,"production_changed":False}
            (case_out/"REPORT.json").write_text(json.dumps(report,indent=2)+"\n");reports.append(report);client.close()
    assert traversals==8
    final={"schema":"live-infinita-bounded-contact-search-comparison/v1","sdk_commit":SDK_COMMIT,"actual_native_traversals":8,
        "actual_facts_confirmed_and_recovered":4,"cold_recoveries":4,"cases":reports,"production_changed":False,"production_benefit_demonstrated":False,
        "limits":["Same sighted target in both arms isolates contact-search behavior; this stage does not compare memory-based target selection.",
            "Recovery results are execution diagnostics, not successful approach facts in the learning core.",
            "Flat terrain, prescribed animal turns and temporary occlusion; no ecology, capture, camera rendering or production integration.",
            "At most 32 searches per process and one per prior approach id; restart persistence is not implemented and the component is not enabled in production."]}
    (out/"CONTACT_SEARCH_008FO.json").write_text(json.dumps(final,indent=2)+"\n")
    print("008FO_CONTACT_SEARCH_PASS traversals=8 actual_facts=4 cold_recoveries=4")
if __name__=="__main__":main()
