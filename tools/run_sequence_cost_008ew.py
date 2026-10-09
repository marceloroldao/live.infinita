#!/usr/bin/env python3
"""Matched successive physical changes, with real cold core recovery between phases."""
import argparse,json,os,pathlib,re,subprocess,sys,tempfile
import run_native_patterns_008eh as native
from nov_navigation_pattern_sync import sync_once
OPENINGS=(-20,-110,0,-20)
SCRIPT=native.ROOT/"tests/godot_sequence_cost_008ew.gd"

def run(project,out):
    out.mkdir(parents=True,exist_ok=True)
    sys.path.insert(0,str(native.SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008ew-sequence-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall=[tmp/n for n in ("fixture.json","state.json","world.json","checkpoint.json","recall.json")]
        world.write_text(json.dumps({"world_id":"native-pattern-008eh"}))
        def physical(phase,opening=None):
            env=dict(os.environ,LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),
                LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state),LIVE_INFINITA_SEQUENCE_PHASE=phase,
                LIVE_INFINITA_NAVIGATION_COST_SHIFT="1",LIVE_INFINITA_NAVIGATION_CONTACT_TURNS="1",
                LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION="1",XDG_DATA_HOME=str(tmp/"userdata"))
            env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL",None)
            if opening is not None:
                env.update(LIVE_INFINITA_SEQUENCE_OPENING=str(opening),LIVE_INFINITA_PHYSICAL_MEMORY_RECALL=str(recall))
            p=subprocess.run([native.ENGINE,"--headless","--audio-driver","Dummy","--path",str(project),
                "--script",str(SCRIPT),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=180)
            log=p.stdout+p.stderr;(out/(phase+".txt")).write_text(log)
            if re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M):
                raise RuntimeError(log[-6000:])
            results=[json.loads(l.split(" ",1)[1]) for l in p.stdout.splitlines() if l.startswith("008EH_NATIVE_PATTERN_COMPARISON ")]
            assert len(results)==1,log[-6000:]
            result=results[0]
            (out/(phase+".json")).write_text(json.dumps(result,indent=2)+"\n")
            facts=json.loads(fixture.read_text())
            (out/(phase+"_facts.json")).write_text(json.dumps(facts,indent=2)+"\n")
            assert p.returncode==0 and result["failures"]==0, "Physical failure archived; do not omit this phase"
            for row in result["runs"]:
                assert all(row["status"][k] for k in ("cost_shift_enabled","exit_direction_enabled","local_turn_continuity_enabled"))
                assert row["arrived"] and row["collisions"]==0 and not row["rescued"] and row["route_plan_builds"]==0
            return result,facts
        key="isolated-sequence-"+("x"*32)
        service=client=None
        def connect():
            nonlocal service,client
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI();attach_structural_observation_routes(app,api_key=key,service=service)
            client=TestClient(app)
        def send(row):
            r=client.post("/api/v1/structural/observations?defer_associations=true",json=row,headers={"X-Memoria-Key":key})
            assert r.status_code==201,r.text
            return r.json()
        def fetch():
            r=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert r.status_code==200,r.text
            return r.json()
        stored=0
        def durable(facts):
            nonlocal stored,service,client
            batches=[]
            for _ in range(20):
                batch=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch);batches.append(batch)
                if batch["acked"]==0:break
            stored+=len(facts["rows"])
            assert service.store.count==stored<=64
            expected=json.loads(recall.read_text())["entries"]
            assert len(expected)==stored
            client.close();client=None;service=None
            connect();recall.unlink()
            def forbidden(_):raise AssertionError("Cold recovery cannot reingest physical outcomes")
            recovered=sync_once(fixture,world,checkpoint,recall,send=forbidden,fetch=fetch)
            actual=json.loads(recall.read_text())["entries"]
            assert recovered["acked"]==0 and actual==expected and service.store.count==stored
            (out/("recovered_"+str(stored)+".json")).write_text(json.dumps(actual,indent=2)+"\n")
            return {"intake":batches,"recovery_without_cache_or_reingest":recovered,"stored":stored}
        training,facts=physical("training")
        assert len(facts["rows"])==4
        connect();recoveries=[durable(facts)]
        phases=[]
        for index,opening in enumerate(OPENINGS):
            phase,facts=physical("phase_"+str(index),opening)
            assert len(phase["runs"])==24 and len(facts["rows"])==12
            known_ids={row["observation_id"] for row in json.loads(recall.read_text())["entries"]}
            assert phase["runs"][1]["recommendation"].get("source")=="recovered-pattern-evidence"
            pairs=[]
            for i in range(12):
                b,c=phase["runs"][2*i:2*i+2]
                assert b["arm"].endswith("_perception_"+str(i)) and c["arm"].endswith("_memory_"+str(i))
                assert not b["status"]["enabled"] and c["status"]["enabled"]
                assert c["status"]["recovered_records"]==stored
                assert c["status"]["ram_records"]==i+1
                if c["recommendation"].get("source")=="recovered-pattern-evidence":
                    ids=c["recommendation"].get("observation_ids",[])
                    assert ids and set(ids)<=known_ids
                pairs.append({"trial":i+1,"perception":b,"memory":c,
                    "saving_m":b["distance_m"]-c["distance_m"],
                    "saving_simulated_s":b["simulated_seconds"]-c["simulated_seconds"]})
            summary={"phase":index,"opening_z":opening,"pairs":pairs,
                "total_saving_m":sum(p["saving_m"] for p in pairs),
                "total_saving_simulated_s":sum(p["saving_simulated_s"] for p in pairs),
                "sides":[p["memory"]["side"] for p in pairs],
                "sources":[p["memory"]["recommendation"].get("source","perception") for p in pairs],
                "censored_contacts":sum(sum(p["memory"]["status"]["exclusions"].values()) for p in pairs),
                "pending_contacts_at_end":sum(p["memory"]["status"]["pending_contacts"] for p in pairs)}
            phases.append(summary);recoveries.append(durable(facts))
            print(json.dumps({k:v for k,v in summary.items() if k!="pairs"}),flush=True)
        client.close();client=None;service=None
        memory=[r for r in training["runs"] if r["arm"].startswith("training_memory_")]
        baseline=[r for r in training["runs"] if r["arm"].startswith("training_perception_")]
        assert len(memory)==len(baseline)==4
        pairs=[p for phase in phases for p in phase["pairs"]]
        accounting={}
        for metric,saving in (("distance_m","saving_m"),("simulated_seconds","saving_simulated_s")):
            acq=sum(r[metric] for r in memory);control=sum(r[metric] for r in baseline);extra=acq-control
            prefixes=[];cumulative=0
            for p in pairs:
                cumulative+=p[saving]
                prefixes.append({"post_training_trial":len(prefixes)+1,
                    "net_after_full_acquisition":cumulative-acq,
                    "net_vs_same_tasks_perception":cumulative-extra})
            def durable_crossing(key):
                return next((p["post_training_trial"] for i,p in enumerate(prefixes)
                    if all(x[key]>=0 for x in prefixes[i:])),None)
            accounting[metric]={"acquisition_total":acq,"acquisition_same_tasks_control":control,
                "acquisition_extra":extra,"adaptation_and_reuse_saving":cumulative,
                "net_after_full_acquisition":cumulative-acq,
                "net_vs_same_tasks_perception":cumulative-extra,"prefixes":prefixes,
                "first_trial_remaining_nonnegative_in_observed_sequence_full_cost":durable_crossing("net_after_full_acquisition"),
                "first_trial_remaining_nonnegative_in_observed_sequence_matched_cost":durable_crossing("net_vs_same_tasks_perception")}
        result={"schema":"live-infinita-successive-change-cost/v1","sdk_commit":native.SDK_COMMIT,
            "planned_openings":list(OPENINGS),"trials_per_phase":12,"training":training,"phases":phases,
            "cost_accounting":accounting,"durable_recoveries":recoveries,"stored_actual_physical_facts":stored,
            "actual_control_traversals":52,"actual_memory_traversals":52,
            "production_benefit_demonstrated":False,"production_changed":False,
            "scope":"current policy; matched actual flat-wall physics; cold isolated real core between changes",
            "limits":["Single related geometry family; deterministic trials are not independent statistical samples.",
                "New local outcomes merge with recovered core history during each phase; core is updated at phase boundaries.",
                "Simulated movement time excludes CPU, database, SDK and network cost.",
                "All measured traversals arrived; failure penalties are not exercised.",
                "No extrapolated break-even is reported; prefix crossings refer only to this observed sequence."]}
        (out/"SEQUENCE_COST_008EW.json").write_text(json.dumps(result,indent=2)+"\n")
        print(json.dumps({"distance":{k:v for k,v in accounting["distance_m"].items() if k!="prefixes"},
            "simulated_time":{k:v for k,v in accounting["simulated_seconds"].items() if k!="prefixes"}}))
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True)
    a=p.parse_args();run(a.project,a.output_dir)
if __name__=="__main__":main()
