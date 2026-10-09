#!/usr/bin/env python3
"""Actual corners, U pockets and closed-enclosure failures, with isolated real core."""
import argparse,collections,json,math,os,pathlib,re,subprocess,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
SCRIPT=native.ROOT/"tests/godot_obstacle_failure_008ex.gd"
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True);a=p.parse_args()
    a.output_dir.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    summaries=[]
    for geometry in ("corner","pocket","closed"):
        with tempfile.TemporaryDirectory(prefix="008ex-"+geometry+"-") as raw:
            tmp=pathlib.Path(raw)
            fixture,state,world,checkpoint,recall=[tmp/n for n in ("facts.json","state.json","world.json","checkpoint.json","recall.json")]
            def physical(cold=False):
                env=dict(os.environ,LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state),
                    LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),LIVE_INFINITA_OBSTACLE_GEOMETRY=geometry,
                    LIVE_INFINITA_NAVIGATION_COST_SHIFT="1",LIVE_INFINITA_NAVIGATION_CONTACT_TURNS="1",
                    LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION="1",XDG_DATA_HOME=str(tmp/"userdata"))
                env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL",None)
                if cold:env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"]=str(recall)
                phase=geometry+("_cold" if cold else "_acquisition")
                result=subprocess.run([native.ENGINE,"--headless","--audio-driver","Dummy","--path",str(a.project),
                    "--script",str(SCRIPT),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=240)
                log=result.stdout+result.stderr;(a.output_dir/(phase+".txt")).write_text(log)
                if re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):
                    raise RuntimeError(log[-6000:])
                rows=[json.loads(l.split(" ",1)[1]) for l in result.stdout.splitlines() if l.startswith("008EX_OBSTACLE_FAILURE ")]
                assert len(rows)==1,log[-6000:]
                data=rows[0];(a.output_dir/(phase+".json")).write_text(json.dumps(data,indent=2)+"\n")
                assert result.returncode==0 and data["failures"]==0
                assert len(data["runs"])==(2 if cold else 16)
                for r in data["runs"]:
                    assert all(r["status"][k] for k in ("cost_shift_enabled","exit_direction_enabled","local_turn_continuity_enabled"))
                    assert r["collisions"]==0 and r["route_plan_builds"]==0
                    assert r["termination"] in ("arrived","stuck_recovery","interrupted")
                    assert (r["termination"]=="stuck_recovery")==r["watchdog_stop"]
                return data
            acquisition=physical()
            facts=json.loads(fixture.read_text())
            (a.output_dir/(geometry+"_facts.json")).write_text(json.dumps(facts,indent=2)+"\n")
            assert facts["rows"] and len(facts["rows"])<=64
            world.write_text(json.dumps({"world_id":acquisition["world_id"]}))
            key="isolated-obstacles-"+("x"*32)
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
            batches=[]
            for _ in range(20):
                batch=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch);batches.append(batch)
                if batch["acked"]==0:break
            expected=json.loads(recall.read_text())["entries"]
            assert service.store.count==len(expected)==len(facts["rows"])
            client.close();del service
            service,client=connect();recall.unlink()
            def forbidden(_):raise AssertionError("Cold recovery cannot reingest actual outcomes")
            recovery=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
            assert recovery["acked"]==0 and json.loads(recall.read_text())["entries"]==expected
            assert service.store.count==len(facts["rows"])
            client.close();del service
            (a.output_dir/(geometry+"_recovered.json")).write_text(json.dumps(expected,indent=2)+"\n")
            cold=physical(True)
            b,c=cold["runs"]
            assert c["status"]["recovered_records"]==len(expected)
            all_rows=acquisition["runs"]+cold["runs"]
            if c["recommendation"].get("source")=="recovered-pattern-evidence":
                ids=c["recommendation"].get("observation_ids",[])
                assert ids and set(ids)<={r["observation_id"] for r in expected}
            failure_penalty_checked=False
            if geometry=="closed":
                assert all(r["termination"]=="stuck_recovery" and r["watchdog_stop"] for r in all_rows)
                assert all(r["outcome"]=="stuck_recovery" and r["completion_basis"]=="stuck_recovery" for r in facts["rows"])
                evaluation=c["initial_evaluation"]
                assert evaluation["reason"]=="side_without_success" and not c["recommendation"]
                for side in ("-1","1"):
                    selected=[r for r in expected if r["context"]==evaluation["context"] and r["side"]==int(side)]
                    alt=evaluation["alternatives"][side]
                    assert alt["samples"]==alt["errors"]==len(selected)>0
                    measured_cost=sum(min(r["distance_m"]/3,100) for r in selected)/len(selected)
                    assert math.isclose(alt["score"],measured_cost+20,abs_tol=1e-6)
                failure_penalty_checked=True
            controls=acquisition["runs"][0::2]+[b]
            memory=acquisition["runs"][1::2]+[c]
            assert len(controls)==len(memory)==9
            def measured(rows):
                return {"traversals":len(rows),"arrivals":sum(r["arrived"] for r in rows),
                    "terminations":dict(collections.Counter(r["termination"] for r in rows)),
                    "distance_m":sum(r["distance_m"] for r in rows),
                    "simulated_seconds":sum(r["simulated_seconds"] for r in rows)}
            summary={"geometry":geometry,"control":measured(controls),"memory":measured(memory),
                "same_nine_tasks_distance_delta_m":sum(r["distance_m"] for r in memory)-sum(r["distance_m"] for r in controls),
                "cold_pair_distance_delta_m":c["distance_m"]-b["distance_m"],
                "cold_pair_same_completion":c["arrived"]==b["arrived"],
                "cold_recommendation":c["recommendation"],"cold_decision_status":c["status"],
                "stored_real_outcomes":len(facts["rows"]),
                "real_recovered_failure_penalty_checked":failure_penalty_checked,
                "outcome_counts":dict(collections.Counter(r["outcome"] for r in facts["rows"])),
                "actual_censored_contacts":sum(sum(r["status"]["exclusions"].values()) for r in all_rows),
                "pending_at_end":sum(r["status"]["pending_contacts"] for r in all_rows),
                "intake":batches,"cold_recovery":recovery,
                "distance_reduction_is_performance_benefit_only_if_tasks_complete":True}
            summaries.append(summary);print(json.dumps({k:summary[k] for k in ("geometry","control","memory","outcome_counts","cold_pair_distance_delta_m")}),flush=True)
    result={"schema":"live-infinita-obstacle-failure-matrix/v1","sdk_commit":native.SDK_COMMIT,
        "cases":summaries,"actual_traversals":54,"production_changed":False,"production_benefit_demonstrated":False,
        "scope":"three isolated deterministic physical fixtures; per-case acquired evidence; same current navigation flags",
        "limits":["Each geometry has a separate world/core: this does not demonstrate cross-geometry transfer.",
            "All failure distances and time remain counted; shorter failed travel is not success.",
            "Closed enclosure is physically unreachable; no memory can create an exit.",
            "Simulated movement time excludes SDK/database/network/CPU overhead.",
            "Native local contact outcomes are distinct from whole-journey completion.",
            "Eight acquisition tasks and one cold validation are included per arm; repeats are not independent samples."]}
    (a.output_dir/"OBSTACLE_FAILURE_008EX.json").write_text(json.dumps(result,indent=2)+"\n")
if __name__=="__main__":main()
