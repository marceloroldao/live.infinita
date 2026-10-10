#!/usr/bin/env python3
"""Actual interrupted/native trajectories, cold renderer and core, durable attempt guard."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT,ENGINE
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_context_sync import sync_once
from nov_animal_exploration_guard import recommend_and_reserve,settle
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
WORLD="approach-native-transfer-008fi"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);cases=[];movements=0
    with tempfile.TemporaryDirectory(prefix="008fk-exploration-guard-") as folder:
        for mode in ("interrupted","completed"):
            tmp=pathlib.Path(folder)/mode;tmp.mkdir();case_out=out/mode;case_out.mkdir(exist_ok=True)
            world,checkpoint,recall,guard=[tmp/n for n in ("world","checkpoint","recall","guard")]
            world.write_text(json.dumps({"world_id":WORLD}));key="isolated-attempt-guard-"+("x"*32)
            rows=[];cold_reports=[]
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
            def env_for(state,target,clock,serial,wall,interrupt=False):
                return dict(os.environ,LIVE_INFINITA_APPROACH_CONTEXT_TEST_STATE=str(state),LIVE_INFINITA_APPROACH_TEST_CLOCK=str(clock),
                    LIVE_INFINITA_APPROACH_TEST_TARGET=target,LIVE_INFINITA_APPROACH_TEST_REVERSE="0",XDG_DATA_HOME=str(tmp/"userdata"),
                    LIVE_INFINITA_TRANSFER_ANIMAL_SERIAL=str(serial),LIVE_INFINITA_TRANSFER_WALL_AT=str(wall),LIVE_INFINITA_GUARD_INTERRUPT="1" if interrupt else "0",
                    LIVE_INFINITA_TRANSFER_SPEED="4",LIVE_INFINITA_TRANSFER_NEAR="16",LIVE_INFINITA_TRANSFER_FAR="22",LIVE_INFINITA_TRANSFER_WALL_LENGTH="80")
            def invoke(script,env,label,prefix):
                run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests"/script)],
                    env=env,capture_output=True,text=True,timeout=60)
                log=run.stdout+run.stderr;(case_out/(label+".log")).write_text(log)
                assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
                vals=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith(prefix+" ")]
                assert len(vals)==1
                return vals[0]
            def physical(label,target,clock,serial=0,wall=6,interrupt=False):
                nonlocal movements
                state=tmp/label;env=env_for(state,target,clock,serial,wall,interrupt)
                script="godot_approach_interruption_008fk.gd" if interrupt else "godot_approach_native_transfer_008fi.gd"
                d=invoke(script,env,label,"008FK_INTERRUPTED" if interrupt else "008FI_PHYSICAL")
                if interrupt or not d["probe"]:movements+=1
                (case_out/(label+".json")).write_text(json.dumps(d,indent=2)+"\n")
                return d,pathlib.Path(str(state)+".context"),state
            def mirror_and_cold(source,actual=None):
                nonlocal service,client
                ack=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch)
                assert ack["acked_this_poll"]==(1 if actual is not None else 0)
                if actual is not None:rows.append(actual)
                expected=json.loads(recall.read_text())["entries"]
                client.close();client=None;service=None;service,client=connect();recall.unlink()
                def forbidden(_):raise AssertionError("Cold retrieval must not POST")
                cold=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
                known=json.loads(recall.read_text())["entries"]
                assert cold["acked_this_poll"]==0 and known==expected and service.store.count==len(rows)==cold["cached_recovered"]
                actual_rows=sorted([{k:v for k,v in e.items() if k!="observation_id"} for e in known],key=lambda r:r["approach"]["id"])
                assert actual_rows==sorted(rows,key=lambda r:r["approach"]["id"])
                cold_reports.append(cold);return known
            for i in range(4):
                d,source,_=physical("acquisition_"+str(i),WORLD+":rabbit:"+str(i%2),100000+i*30000)
                assert d["fact"]["result"]==("contact_lost" if i%2==0 else "approached")
                known=mirror_and_cold(source,d["context_fact"])
            attempts=[]
            for i in range(4 if mode=="interrupted" else 5):
                clock=400000+i*12000
                probe,_,_=physical("probe_"+str(i),"",clock,20,12.5)
                decision=recommend_and_reserve(guard,probe["candidates"],known,WORLD,clock)
                token=decision["reservation_token"]
                if i<4:
                    assert token and decision["source"]=="recovered-cost-revalidation"
                    duplicate=recommend_and_reserve(guard,probe["candidates"],known,WORLD,clock)
                    assert duplicate["reason"]=="pending_reservation" and duplicate["entity_id"] is None
                else:assert token is None and decision["source"]=="perception"
                d,source,state=physical("attempt_"+str(i),decision["entity_id"],clock,20,12.5,mode=="interrupted")
                if mode=="interrupted":
                    assert d["actual_steps"]==5 and d["partial_distance_m"]>0
                    base_sealed=json.loads(state.read_text())
                    pending=json.loads(base_sealed["payload"])["pending"]
                    assert pending==d["pending"] and pending["distance_m"] is None and not pending["learning_eligible"]
                    restart=invoke("godot_approach_restart_008fk.gd",env_for(state,"",clock,20,12.5),"restart_"+str(i),"008FK_RESTART")
                    assert restart["id"]==pending["id"] and restart["ended_ms"] is None and restart["distance_m"] is None
                    status=settle(guard,token,restart);assert status=="interrupted"
                    assert json.loads(json.loads(source.read_text())["payload"])["records"]==[]
                    known=mirror_and_cold(source)
                    actual=restart
                    (case_out/("attempt_"+str(i)+"_base_cold.json")).write_bytes(state.read_bytes())
                else:
                    assert d["fact"]["result"]=="approached"
                    if token:assert settle(guard,token,d["fact"])=="closed"
                    known=mirror_and_cold(source,d["context_fact"]);actual=d["fact"]
                (case_out/("attempt_"+str(i)+"_source.json")).write_bytes(source.read_bytes())
                attempts.append({"decision":decision,"movement":d,"settled_base_outcome":actual,"core_count":service.store.count})
                print("008FK_ATTEMPT",mode,i,"interrupted" if mode=="interrupted" else d["fact"]["result"],flush=True)
            if mode=="interrupted":
                probe,_,_=physical("budget_exhausted_probe","",460000,20,12.5)
                stopped=recommend_and_reserve(guard,probe["candidates"],known,WORLD,460000)
                assert stopped["reason"]=="exploration_budget_exhausted" and stopped["reservation_token"] is None
                assert service.store.count==4
            else:
                stopped=attempts[-1]["decision"];assert service.store.count==9
            sealed_guard=json.loads(guard.read_text());guard_snapshot=json.loads(sealed_guard["payload"])
            reservations=guard_snapshot["worlds"][WORLD]["reservations"]
            assert len(reservations)==4 and all(r["status"]==("interrupted" if mode=="interrupted" else "closed") for r in reservations)
            report={"case":mode,"attempts":attempts,"final_decision":stopped,"guard_snapshot":guard_snapshot,
                "facts_confirmed_and_cold_recovered":len(rows),"cold_recoveries":cold_reports,"production_changed":False}
            (case_out/"REPORT.json").write_text(json.dumps(report,indent=2)+"\n");cases.append(report);client.close()
    assert movements==17
    final={"schema":"live-infinita-durable-exploration-guard-validation/v1","sdk_commit":SDK_COMMIT,"physical_movements":17,
        "completed_movements":13,"interrupted_movements":4,"actual_facts_confirmed_and_recovered":13,"cold_core_recoveries":17,
        "cold_renderer_reloads":4,"cases":cases,"production_changed":False,"production_benefit_demonstrated":False,
        "limits":["Reservation journal is a private execution guard, not a fact or inference in the learning core.",
            "Four exploratory starts per world/logical epoch include interruptions; ordinary perception/exploitation choices do not consume that quota.",
            "Pending reservation blocks a second launch even across epoch change; only an actual matching history record settles it.",
            "One serial actor and local filesystem locking; no distributed workers or full live camera integration tested.",
            "Flat terrain, stationary animals, controlled attention and designed scenarios; no production policy installation."]}
    (out/"EXPLORATION_GUARD_008FK.json").write_text(json.dumps(final,indent=2)+"\n")
    print("008FK_EXPLORATION_GUARD_PASS movements=17 completed=13 interrupted=4 facts=13 core_recoveries=17 renderer_reloads=4")
if __name__=="__main__":main()
