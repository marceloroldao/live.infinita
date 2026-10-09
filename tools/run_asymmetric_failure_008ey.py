#!/usr/bin/env python3
"""Actual deterministic trap vs viable route, cold recovered real physical evidence."""
import argparse,collections,json,os,pathlib,re,subprocess,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
SCRIPT=native.ROOT/"tests/godot_asymmetric_failure_008ey.gd"
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    parser.add_argument("--output-dir",type=pathlib.Path,required=True)
    parser.add_argument("--experimental-assessment",action="store_true",help="Reuse archived physical acquisition, assess isolated candidate and diagnostic ablations")
    a=parser.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008ey-asymmetric-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall=[tmp/n for n in ("facts.json","state.json","world.json","checkpoint.json","recall.json")]
        def physical(cold=False):
            env=dict(os.environ,LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state),
                LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),LIVE_INFINITA_NAVIGATION_COST_SHIFT="1",
                LIVE_INFINITA_NAVIGATION_CONTACT_TURNS="1",LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION="1",
                XDG_DATA_HOME=str(tmp/"userdata"))
            env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL",None)
            if cold:env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"]=str(recall)
            env.pop("LIVE_INFINITA_FAILURE_POLICY_008EY",None)
            if a.experimental_assessment:env["LIVE_INFINITA_FAILURE_POLICY_008EY"]="candidate"
            name=("experimental_cold" if a.experimental_assessment else "cold") if cold else "acquisition"
            p=subprocess.run([native.ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),
                "--script",str(SCRIPT),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=240)
            log=p.stdout+p.stderr;(a.output_dir/(name+".txt")).write_text(log)
            if re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):raise RuntimeError(log[-6000:])
            rows=[json.loads(l.split(" ",1)[1]) for l in p.stdout.splitlines() if l.startswith("008EY_ASYMMETRIC_FAILURE ")]
            assert len(rows)==1,log[-6000:]
            data=rows[0];(a.output_dir/(name+".json")).write_text(json.dumps(data,indent=2)+"\n")
            assert p.returncode==0 and data["failures"]==0
            for row in data["runs"]:
                assert row["collisions"]==0 and row["route_plan_builds"]==0
                assert all(row["status"][k] for k in ("cost_shift_enabled","exit_direction_enabled","local_turn_continuity_enabled"))
            return data
        if a.experimental_assessment:
            training=json.loads((a.output_dir/"acquisition.json").read_text())
            fixture.write_text((a.output_dir/"physical_facts.json").read_text())
        else:training=physical()
        assert len(training["runs"])==16
        facts=json.loads(fixture.read_text())
        (a.output_dir/"physical_facts.json").write_text(json.dumps(facts,indent=2)+"\n")
        assert facts["rows"] and len(facts["rows"])<=64
        world.write_text(json.dumps({"world_id":training["world_id"]}))
        key="isolated-asymmetric-"+("x"*32)
        def connect():
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            return service,TestClient(app)
        service,client=connect()
        def send(row):
            r=client.post("/api/v1/structural/observations?defer_associations=true",json=row,headers={"X-Memoria-Key":key})
            assert r.status_code==201,r.text
            return r.json()
        def fetch():
            r=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert r.status_code==200,r.text
            return r.json()
        intake=[]
        for _ in range(20):
            batch=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch);intake.append(batch)
            if batch["acked"]==0:break
        expected=json.loads(recall.read_text())["entries"]
        assert service.store.count==len(expected)==len(facts["rows"])
        client.close();del service
        service,client=connect();recall.unlink()
        def forbidden(_):raise AssertionError("Cold recovery must not reingest")
        recovery=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
        assert recovery["acked"]==0 and json.loads(recall.read_text())["entries"]==expected
        assert service.store.count==len(expected)
        client.close();del service
        (a.output_dir/("experimental_recovered.json" if a.experimental_assessment else "recovered.json")).write_text(json.dumps(expected,indent=2)+"\n")
        cold=physical(True)
        assert len(cold["runs"])==(4 if a.experimental_assessment else 2)
        if a.experimental_assessment:
            full,positive,no_penalty=cold["runs"][1:]
            assert full["arrived"] and no_penalty["arrived"] and not positive["arrived"]
            assert full["recommendation"].get("source")=="recovered-pattern-evidence"
            assert full["recommendation"].get("observation_ids")
            assert set(full["recommendation"]["observation_ids"])<={r["observation_id"] for r in expected}
            assert full["status"]["core_changed_initial_decisions"]==1
            assert positive["status"]["recovered_records"]==2
            assert full["status"]["recovered_records"]==no_penalty["status"]["recovered_records"]==len(expected)
        def cost(rows):
            return {"attempts":len(rows),"arrivals":sum(r["arrived"] for r in rows),
                "terminations":dict(collections.Counter(r["termination"] for r in rows)),
                "distance_m":sum(r["distance_m"] for r in rows),
                "simulated_seconds":sum(r["simulated_seconds"] for r in rows)}
        result={"schema":"live-infinita-asymmetric-failure/v1","sdk_commit":native.SDK_COMMIT,
            "training":training,"cold":cold,"intake":intake,"cold_recovery":recovery,
            "persisted_outcomes":dict(collections.Counter(r["outcome"] for r in facts["rows"])),
            "control":cost(training["runs"][::2]+cold["runs"][:2:2]),
            "memory":cost(training["runs"][1::2]+cold["runs"][1:2:2]),
            "production_changed":False,"production_benefit_demonstrated":False,
            "experimental_policy_assessed":a.experimental_assessment,
            "diagnostic_ablations_not_in_primary_paired_budget":cold["runs"][2:],
            "limits":["Dynamic one-way trap resets identically per attempt; closure reacts only to real occupied position.",
                "All failed effort remains counted. No shorter failed journey is called a successful gain.",
                "One isolated deterministic fixture, no broad or production benefit claim.",
                "Simulated time excludes compute, SDK/database and network costs."]}
        (a.output_dir/("EXPERIMENTAL_FAILURE_008EY.json" if a.experimental_assessment else "ASYMMETRIC_FAILURE_008EY.json")).write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"control":result["control"],"memory":result["memory"],
            "persisted":result["persisted_outcomes"],"cold":[{k:r[k] for k in ("arrived","side","gate_closed","termination")} for r in cold["runs"]],
            "cold_reason":cold["runs"][-1]["initial_evaluation"].get("reason")}))
if __name__=="__main__":main()
