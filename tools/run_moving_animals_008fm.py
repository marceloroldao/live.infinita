#!/usr/bin/env python3
"""Moving collidable animals: recovered choices versus nearest-target perception."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from nov_animal_approach_context import recommend as previous_recommend
from nov_animal_exploration_guard import recommend_and_reserve,settle
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-moving-animals-008fm"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);reports=[];traversals=0
    with tempfile.TemporaryDirectory(prefix="008fm-cost-refresh-") as folder:
        for name,animal_speed in (("slow",0.5),("faster",1.5)):
            wall=6.0
            tmp=pathlib.Path(folder)/name;tmp.mkdir()
            world,checkpoint,recall,guard=[tmp/n for n in ("world","checkpoint","recall","guard")]
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
            def physical(label,target,clock,serial=0,wall_at=6):
                nonlocal traversals
                state=tmp/label
                env=dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                    LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_REVERSE="0",XDG_DATA_HOME=str(tmp/"userdata"),
                    LIVE_INFINITA_TRANSFER_ANIMAL_SERIAL=str(serial),LIVE_INFINITA_TRANSFER_WALL_AT=str(wall_at),
                    LIVE_INFINITA_TEST_ANIMAL_SPEED=str(animal_speed),LIVE_INFINITA_TRANSFER_SPEED="4",LIVE_INFINITA_TRANSFER_NEAR="16",LIVE_INFINITA_TRANSFER_FAR="22",
                    LIVE_INFINITA_TRANSFER_WALL_LENGTH="80")
                run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_moving_animals_008fm.gd")],
                    env=env,capture_output=True,text=True,timeout=60)
                log=run.stdout+run.stderr;(case_out/(label+".log")).write_text(log)
                assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
                vals=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FM_PHYSICAL ")]
                assert len(vals)==1
                d=vals[0]
                source=pathlib.Path(str(state)+".context")
                if not d["probe"]:
                    traversals+=1
                    assert d["contacts"]==0 and d["route_plan_builds"]==0
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
            acquisition=[]
            for i in range(4):
                d,source=physical("acquisition_"+str(i),WORLD+":rabbit:"+str(i%2),100000+i*20000)
                assert d["animal_steps"]>0 and not d["future_position_given_to_controller"]
                known=store_and_cold(d,source);acquisition.append(d)
            pairs=[]
            for i in range(4):
                clock=200000+i*20000
                probe,_=physical("probe_"+str(i),"",clock,20,wall)
                candidates=probe["candidates"]
                decision=recommend_and_reserve(guard,candidates,known,WORLD,clock)
                control_decision=previous_recommend(candidates,[],WORLD,clock)
                assert control_decision["entity_id"]==WORLD+":rabbit:20"
                adaptive,source=physical("adaptive_"+str(i),decision["entity_id"],clock,20,wall)
                control,_=physical("frozen_"+str(i),control_decision["entity_id"],clock,20,wall)
                assert candidates==adaptive["candidates"]==control["candidates"] and adaptive["fixture"]==control["fixture"]
                assert adaptive["animal_steps"]>0 and control["animal_steps"]>0
                assert not adaptive["future_position_given_to_controller"] and not control["future_position_given_to_controller"]
                if decision["reservation_token"]:assert settle(guard,decision["reservation_token"],adaptive["fact"])=="closed"
                known=store_and_cold(adaptive,source)
                pairs.append({"decision":decision,"adaptive":adaptive,"control_decision":control_decision,"perception_control":control,
                              "control_outcome_ingested":False})
                print("008FM_PAIR",name,i,decision["source"],adaptive["fact"]["result"],flush=True)
            total_adaptive=sum(v["adaptive"]["distance_m"] for v in pairs)
            total_control=sum(v["perception_control"]["distance_m"] for v in pairs)
            assert len(rows)==len(cold_reports)==8
            report={"case":name,"acquisition":acquisition,"pairs":pairs,"persisted_actual_facts":rows,"cold_recoveries":cold_reports,
                "animal_speed_m_s":animal_speed,"exploration_reservations":sum(bool(v["decision"]["reservation_token"]) for v in pairs),"adaptive_total_distance_m":total_adaptive,"perception_total_distance_m":total_control,
                "adaptive_successes":sum(v["adaptive"]["fact"]["result"]=="approached" for v in pairs),
                "perception_successes":sum(v["perception_control"]["fact"]["result"]=="approached" for v in pairs),"production_changed":False}
            (case_out/"REPORT.json").write_text(json.dumps(report,indent=2)+"\n");reports.append(report);client.close()
    assert traversals==24
    final={"schema":"live-infinita-moving-animal-memory-comparison/v1","sdk_commit":SDK_COMMIT,"actual_native_traversals":24,
        "actual_facts_confirmed_and_recovered":16,"cold_recoveries":16,"cases":reports,"production_changed":False,"production_benefit_demonstrated":False,
        "limits":[
        "Four paired approaches at each speed against nearest-target perception; designed flat scenes, not a statistical estimate.",
        "Four scheduled initial acquisitions per speed; held-out animal identities differ from acquisition identities. No transfer between speeds is claimed.",
        "Production heading stabilization, body orientation and scan cadence; camera image, terrain streaming and live feed are not exercised.",
        "Animal bodies move through collision queries at prescribed constant velocities; no feeding, fleeing policy, ecology or capture is implemented.",
        "Only fresh physical sightings and recovered actual outcomes are passed to the selectors; fixture velocity and future positions are not inputs.",
        "The learning core stores and recovers structural outcomes; choice and scoring are implemented by the experimental consumer.",
        "Distance must be considered together with success: an early failed approach can be shorter than a successful one."
]}
    (out/"MOVING_ANIMALS_008FM.json").write_text(json.dumps(final,indent=2)+"\n")
    print("008FM_COST_REVALIDATION_PASS traversals=24 actual_facts=16 cold_recoveries=16")
if __name__=="__main__":main()
