"""Read-only production access; Godot fixtures and actual core API use temporary SQLite."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
DEFAULT_CORE="/opt/live-infinita-memoria-core/dfd87c995b50c49b45a9d5dd4c43cce456983d4f/src"

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--core-src",default=DEFAULT_CORE)
    parser.add_argument("--godot-project",required=True,help="Already imported, isolated Godot project")
    parser.add_argument("--engine",default="/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64")
    parser.add_argument("--report",required=True)
    args=parser.parse_args()
    project=Path(args.godot_project).resolve()
    if project == (ROOT/"apps/renderer-godot").resolve():
        raise ValueError("Use an isolated imported Godot project")
    sys.path[:0]=[args.core_src,str(ROOT/"apps/world-runtime")]
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import memoria_resolutiva.product_structural as product
    import nov_navigation_memory_sync as nav
    import nov_navigation_recall_export as recall
    key="isolated-repeat-benchmark-"+"x"*40
    world_id="navigation-repeat-008cl"
    def app_for(service):
        app=FastAPI()
        product.attach_structural_observation_routes(app,api_key=key,service=service)
        return app
    def simulate(report,cache=None):
        command=[args.engine,"--headless","--audio-driver","Dummy","--path",str(project),
                 "--script",str(ROOT/"tests/godot_navigation_repeat_benchmark_008cl.gd"),
                 "--","--offline-tour","--report="+str(report)]
        if cache:command.append("--recall="+str(cache))
        result=subprocess.run(command,capture_output=True,text=True,timeout=45)
        out=result.stdout+result.stderr
        if result.returncode or "SCRIPT ERROR:" in out or "ERROR:" in out:
            raise RuntimeError(out)
        return json.loads(report.read_text())
    with tempfile.TemporaryDirectory(prefix="nov-repeat-008cl-") as directory:
        temp=Path(directory)
        baseline=simulate(temp/"baseline.json")
        steps=baseline["observed_successful_steps"]
        if not steps:raise AssertionError("No completed physical route evidence")
        memory_root=temp/"memory"
        service=product.ProductStructuralObservationService.open(memory_root,backend="sqlite",allow_fallback=False,replay_associations_on_open=False)
        identities=[]
        with TestClient(app_for(service)) as client:
            for item in steps:
                value=nav.payload(item,world_id,"")
                response=client.post("/api/v1/structural/observations?defer_associations=true",json=value,headers={"X-Memoria-Key":key})
                assert response.status_code==201,response.text
                nav._validate_ack(response.json(),value)
                identities.append(response.json()["observation_id"])
        reopened=product.ProductStructuralObservationService.open(memory_root,backend="sqlite",allow_fallback=False,replay_associations_on_open=False)
        world=temp/"world.json";world.write_text(json.dumps({"world_id":world_id}))
        cache=temp/"public"/"recall.json"
        with TestClient(app_for(reopened)) as client:
            def fetch():
                response=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
                assert response.status_code==200,response.text
                return response.json()
            exported=recall.export_once(world,temp/"private.json",cache,fetch=fetch)
        cached=json.loads(cache.read_text())
        assert {row["observation_id"] for row in cached["entries"]}==set(identities)
        repeated=simulate(temp/"repeat.json",cache)
        assert repeated["results"]["without_memory"]==baseline["results"]["without_memory"],"Control run must reproduce baseline exactly"
        assert repeated["results"]["with_memory"]["reached"],"Retrieved route must still reach goal"

        # Reproduce the real core recent() count/read race, using temporary SQLite.
        race_service=product.ProductStructuralObservationService.open(temp/"race",backend="sqlite",allow_fallback=False,replay_associations_on_open=False)
        def append_fixture(i):
            item={"kind":"successful_route_step","key":f"500,0|{i},0","goal":[500,0],"from":[i,0],"to":[i,1],"observed_count":1}
            value=nav.payload(item,"isolated-race-fixture","")
            race_service.store.append(value["event"],provenance=value["provenance"])
        for i in range(100):append_fixture(i)
        original=race_service.store.ordered_from
        next_index=100
        def append_during_read(offset=0,**kwargs):
            nonlocal next_index
            for _ in range(3):
                append_fixture(next_index);next_index+=1
            return original(offset,**kwargs)
        race_service.store.ordered_from=append_during_read
        with TestClient(app_for(race_service)) as client:
            def recent(limit):
                response=client.get(f"/api/v1/structural/observations/recent?limit={limit}",headers={"X-Memoria-Key":key})
                assert response.status_code==200,response.text
                return response.json()
            old=recent(100);new=recent(64)
        assert len(old["items"])==103 and len(new["items"])==67
        results=repeated["results"]
        report={"schema":"live-infinita-navigation-repeat-validation/v1",
            "scope":"isolated_physics_and_real_core_API_temporary_SQLite",
            "production_memory_written":False,"world_write_authority":False,
            "fixture":"physical-U","fixed_delta_seconds":0.1,
            "memory_seed":"completed_first_trial_route_steps_test_fixture_not_RAM_promotions",
            "api_observations_confirmed":len(identities),"api_observations_recovered":exported["cached"],
            "sqlite_reopened":True,"control_reproduced":True,
            "results":results,
            "difference":{"simulated_seconds":results["with_memory"]["simulated_seconds"]-results["without_memory"]["simulated_seconds"],
                "distance_m":results["with_memory"]["distance_m"]-results["without_memory"]["distance_m"],
                "collisions":results["with_memory"]["collisions"]-results["without_memory"]["collisions"]},
            "core_recent_race":{"requested_before":100,"returned_before":len(old["items"]),
                "requested_after":64,"returned_after":len(new["items"]),"concurrent_appends_each_read":3}}
        Path(args.report).write_text(json.dumps(report,indent=2)+"\n")
        print(json.dumps(report,indent=2))
if __name__=="__main__":main()
