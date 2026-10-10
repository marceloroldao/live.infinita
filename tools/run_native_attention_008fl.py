#!/usr/bin/env python3
"""Production heading and scan cadence: guarded cold-core refresh versus frozen preference."""
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
WORLD="approach-native-attention-008fl"
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"));a=p.parse_args()
    out=a.output_dir;out.mkdir(parents=True,exist_ok=True);reports=[];traversals=0
    with tempfile.TemporaryDirectory(prefix="008fl-cost-refresh-") as folder:
        for name,wall in (("changed",12.5),("unchanged",6.0)):
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
                    LIVE_INFINITA_TRANSFER_SPEED="4",LIVE_INFINITA_TRANSFER_NEAR="16",LIVE_INFINITA_TRANSFER_FAR="22",
                    LIVE_INFINITA_TRANSFER_WALL_LENGTH="80")
                run=subprocess.run([ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),"--script",str(ROOT/"tests/godot_approach_native_attention_008fl.gd")],
                    env=env,capture_output=True,text=True,timeout=60)
                log=run.stdout+run.stderr;(case_out/(label+".log")).write_text(log)
                assert run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|^ERROR:",log,re.M),log[-5000:]
                vals=[json.loads(l.split(" ",1)[1]) for l in run.stdout.splitlines() if l.startswith("008FL_PHYSICAL ")]
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
                d,source=physical("acquisition_"+str(i),WORLD+":rabbit:"+str(i%2),100000+i*30000)
                assert d["fact"]["result"]==("contact_lost" if i%2==0 else "approached")
                known=store_and_cold(d,source);acquisition.append(d)
            frozen=json.loads(json.dumps(known));pairs=[]
            for i in range(10):
                clock=400000+i*12000
                probe,_=physical("probe_"+str(i),"",clock,20,wall)
                candidates=probe["candidates"]
                decision=recommend_and_reserve(guard,candidates,known,WORLD,clock)
                control_decision=previous_recommend(candidates,frozen,WORLD,clock)
                assert control_decision["entity_id"]==WORLD+":rabbit:21"
                adaptive,source=physical("adaptive_"+str(i),decision["entity_id"],clock,20,wall)
                control,_=physical("frozen_"+str(i),control_decision["entity_id"],clock,20,wall)
                assert candidates==adaptive["candidates"]==control["candidates"] and adaptive["fixture"]==control["fixture"]
                if i<4:
                    assert decision["source"]=="recovered-cost-revalidation"
                    assert decision["entity_id"]==WORLD+":rabbit:"+str(20+i%2)
                else:
                    assert decision["source"]!="recovered-cost-revalidation"
                    assert adaptive["fact"]["result"]=="approached"
                    assert decision["entity_id"]==WORLD+":rabbit:"+str(20 if name=="changed" else 21)
                assert control["fact"]["result"]=="approached"
                if decision["reservation_token"]:assert settle(guard,decision["reservation_token"],adaptive["fact"])=="closed"
                known=store_and_cold(adaptive,source)
                pairs.append({"decision":decision,"adaptive":adaptive,"control_decision":control_decision,"frozen_control":control,
                              "control_outcome_ingested":False})
                print("008FL_PAIR",name,i,decision["source"],adaptive["fact"]["result"],flush=True)
            total_adaptive=sum(v["adaptive"]["distance_m"] for v in pairs)
            total_control=sum(v["frozen_control"]["distance_m"] for v in pairs)
            successes=sum(v["adaptive"]["fact"]["result"]=="approached" for v in pairs)
            # Early loss of sight truncates distance: shorter failure is not improvement.
            assert successes==(10 if name=="changed" else 8)
            if name=="changed":assert total_adaptive<total_control
            assert len(rows)==len(cold_reports)==14
            report={"case":name,"acquisition":acquisition,"pairs":pairs,"persisted_actual_facts":rows,"cold_recoveries":cold_reports,
                "refresh_probes":4,"later_choices":6,"adaptive_total_distance_m":total_adaptive,"frozen_total_distance_m":total_control,
                "adaptive_successes":sum(v["adaptive"]["fact"]["result"]=="approached" for v in pairs),
                "frozen_successes":10,"production_changed":False}
            (case_out/"REPORT.json").write_text(json.dumps(report,indent=2)+"\n");reports.append(report);client.close()
    assert traversals==48
    final={"schema":"live-infinita-production-heading-comparison/v1","sdk_commit":SDK_COMMIT,"actual_native_traversals":48,
        "actual_facts_confirmed_and_recovered":28,"cold_recoveries":28,"cases":reports,"production_changed":False,"production_benefit_demonstrated":False,
        "limits":["Five-minute logical epochs, two contexts and two completed measured samples per context are explicit experimental rules.",
            "Repeated geometry changes inside one epoch are not covered; censored attempts cannot fill the measured-outcome quota.",
            "Four scheduled initial acquisitions per case; refresh decisions derive from timestamps of recovered facts.",
            "Production heading stabilization and body orientation methods, same scan cadence; isolated flat terrain and stationary animals. Camera image, full terrain streaming and live network are not exercised.",
            "Ten paired approaches per designed case, not a statistical estimate or proof of an optimal refresh interval.",
            "Unchanged environment exposes exploration cost and temporary failures; correction does not eliminate that tradeoff."]}
    (out/"COST_REVALIDATION_008FL.json").write_text(json.dumps(final,indent=2)+"\n")
    print("008FL_COST_REVALIDATION_PASS traversals=48 actual_facts=28 cold_recoveries=28 refresh_probes=8")
if __name__=="__main__":main()
