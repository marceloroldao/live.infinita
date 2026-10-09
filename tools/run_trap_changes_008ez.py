#!/usr/bin/env python3
"""Candidate policy from empty mirrored memory through repeated trap reversals."""
import argparse,collections,json,os,pathlib,re,subprocess,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
SCRIPT=native.ROOT/"tests/godot_trap_changes_008ez.gd"
PLAN=(("training",-1,8),("mirror_cold",-1,1),("change_0",1,12),("change_1",-1,12),("change_2",1,12),("final_cold",1,1))
def run(project,out,integrated=False):
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008ez-trap-changes-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall=[tmp/n for n in ("facts.json","state.json","world.json","checkpoint.json","recall.json")]
        world.write_text(json.dumps({"world_id":"trap-changes-008ez"}))
        key="isolated-trap-changes-"+("x"*32)
        service=client=None
        def connect():
            nonlocal service,client
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            client=TestClient(app)
        connect()
        def send(row):
            r=client.post("/api/v1/structural/observations?defer_associations=true",json=row,headers={"X-Memoria-Key":key})
            assert r.status_code==201,r.text
            return r.json()
        def fetch():
            r=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert r.status_code==200,r.text
            return r.json()
        def physical(phase,sign,count,cold):
            env=dict(os.environ,LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state),
                LIVE_INFINITA_TRAP_PHASE_008EZ=phase,LIVE_INFINITA_TRAP_SIGN_008EZ=str(sign),LIVE_INFINITA_TRAP_TRIALS_008EZ=str(count),
                LIVE_INFINITA_FAILURE_POLICY_008EY="candidate",LIVE_INFINITA_NAVIGATION_COST_SHIFT="1",
                LIVE_INFINITA_NAVIGATION_CONTACT_TURNS="1",LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION="1",XDG_DATA_HOME=str(tmp/"userdata"))
            if integrated:
                env.pop("LIVE_INFINITA_FAILURE_POLICY_008EY",None)
                env["LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE"]="1"
            else:
                env["LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE"]="0"
            env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL",None)
            if cold:env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"]=str(recall)
            p=subprocess.run([native.ENGINE,"--headless","--audio-driver","Dummy","--path",str(project),
                "--script",str(SCRIPT),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=240)
            log=p.stdout+p.stderr;(out/(phase+".txt")).write_text(log)
            if re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):raise RuntimeError(log[-6000:])
            data=[json.loads(l.split(" ",1)[1]) for l in p.stdout.splitlines() if l.startswith("008EZ_TRAP_CHANGES ")]
            assert len(data)==1,log[-6000:]
            result=data[0];facts=json.loads(fixture.read_text())
            (out/(phase+".json")).write_text(json.dumps(result,indent=2)+"\n")
            (out/(phase+"_facts.json")).write_text(json.dumps(facts,indent=2)+"\n")
            assert p.returncode==0 and result["failures"]==0 and len(result["runs"])==2*count
            assert len(facts["rows"])==count
            return result,facts
        stored=0;stages=[];recoveries=[]
        for phase,sign,count in PLAN:
            known=json.loads(recall.read_text())["entries"] if stored else []
            result,facts=physical(phase,sign,count,bool(stored))
            known_ids={r["observation_id"] for r in known}
            pairs=[]
            for i in range(count):
                b,c=result["runs"][2*i:2*i+2]
                assert not b["status"]["enabled"] and c["status"]["enabled"]
                assert c["status"]["failure_preference_enabled"] is integrated
                assert c["status"]["recovered_records"]==stored and c["status"]["ram_records"]==i+1
                for row in (b,c):
                    assert row["collisions"]==0 and row["route_plan_builds"]==0
                    assert row["termination"] in ("arrived","stuck_recovery")
                    assert row["gate_closed"]==(row["termination"]=="stuck_recovery")
                    assert all(row["status"][k] for k in ("cost_shift_enabled","exit_direction_enabled","local_turn_continuity_enabled"))
                if c["recommendation"].get("source")=="recovered-pattern-evidence":
                    ids=c["recommendation"].get("observation_ids",[])
                    assert ids and set(ids)<=known_ids
                pairs.append({"trial":i+1,"perception":b,"candidate":c})
            def totals(rows):
                return {"attempts":len(rows),"arrivals":sum(r["arrived"] for r in rows),
                    "terminations":dict(collections.Counter(r["termination"] for r in rows)),
                    "distance_m":sum(r["distance_m"] for r in rows),
                    "simulated_seconds":sum(r["simulated_seconds"] for r in rows)}
            summary={"phase":phase,"trap_sign":sign,"pairs":pairs,
                "control":totals(result["runs"][::2]),"candidate":totals(result["runs"][1::2]),
                "sides":[p["candidate"]["side"] for p in pairs],
                "sources":[p["candidate"]["recommendation"].get("source","perception") for p in pairs],
                "decision_reasons":[p["candidate"]["initial_evaluation"].get("reason") for p in pairs]}
            stages.append(summary)
            intake=[]
            for _ in range(20):
                batch=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch);intake.append(batch)
                if batch["acked"]==0:break
            stored+=len(facts["rows"])
            expected=json.loads(recall.read_text())["entries"]
            assert service.store.count==len(expected)==stored<=64
            client.close();client=None;service=None;connect();recall.unlink()
            def forbidden(_):raise AssertionError("Reopen must not reingest unchanged physical outcomes")
            recovered=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
            assert recovered["acked"]==0 and json.loads(recall.read_text())["entries"]==expected and service.store.count==stored
            (out/("recovered_"+str(stored)+".json")).write_text(json.dumps(expected,indent=2)+"\n")
            recoveries.append({"after_phase":phase,"stored":stored,"intake":intake,"cold_recovery":recovered})
            print(json.dumps({k:v for k,v in summary.items() if k!="pairs"}),flush=True)
        client.close();client=None;service=None
        control=[p["perception"] for s in stages for p in s["pairs"]]
        candidate=[p["candidate"] for s in stages for p in s["pairs"]]
        result={"schema":"live-infinita-mirrored-changing-trap/v1","sdk_commit":native.SDK_COMMIT,
            "plan":[{"phase":p,"trap_sign":s,"trials":n} for p,s,n in PLAN],"stages":stages,
            "control":totals(control),"candidate":totals(candidate),"actual_traversals":len(control)+len(candidate),
            "durable_recoveries":recoveries,"persisted_actual_facts":stored,
            "production_changed":False,"production_benefit_demonstrated":False,"experimental_policy":not integrated,"native_failure_preference":integrated,
            "limits":["Single constructed dynamic trap family, deterministic paired trajectories.",
                "Perception is the comparison; no current-policy memory arm in this reversal experiment.",
                "All failed costs included; raw movement differences are not completed-task efficiency.",
                "Real core cold-recovered at phase boundaries; fresh local outcomes merge within phase.",
                "Simulated time excludes compute, SDK/database, network and storage overhead."]}
        (out/"TRAP_CHANGES_008EZ.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"control":result["control"],"candidate":result["candidate"],"facts":stored}))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True);a=p.parse_args();run(a.project,a.output_dir)
if __name__=="__main__":main()
