#!/usr/bin/env python3
"""Validate actual native collector -> production bridge -> reopened isolated core."""
import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from run_physical_memory_comparison_008ed import SDK, SDK_COMMIT, ENGINE
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/"apps/world-runtime"))
from nov_navigation_pattern_sync import sync_once, payload
from nov_spatial_memory_sync import _canonical
from hashlib import blake2b, sha256
SCRIPT = ROOT/"tests/godot_native_patterns_008eh.gd"

def godot(project, fixture, state, recall=None):
    env = dict(os.environ, LIVE_INFINITA_PHYSICAL_MEMORY_FIXTURE=str(fixture),
               LIVE_INFINITA_NATIVE_PATTERN_STATE=str(state))
    env.pop("LIVE_INFINITA_PHYSICAL_MEMORY_RECALL", None)
    if recall is not None:
        env["LIVE_INFINITA_PHYSICAL_MEMORY_RECALL"] = str(recall)
    p = subprocess.run([ENGINE, "--headless", "--audio-driver", "Dummy", "--path", str(project),
                        "--script", str(SCRIPT), "--", "--offline-tour"],
                       env=env, capture_output=True, text=True, timeout=60)
    log = p.stdout+p.stderr
    if p.returncode or re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:", log, re.M):
        raise RuntimeError(log[-4000:])
    results = [json.loads(line.split(" ",1)[1]) for line in p.stdout.splitlines()
               if line.startswith("008EH_NATIVE_PATTERN_COMPARISON ")]
    assert len(results)==1 and results[0]["failures"]==0
    return results[0],log

def legacy_contract_fixture(row):
    # Synthetic previous-version envelope for migration testing in the isolated core only.
    fact=dict(row)
    fact.pop("completion_basis");fact.pop("exit_progress_m")
    previous="capsule044-height18-lookahead3-contour64-v1"
    fact["context"]=fact["context"].replace(fact["profile"],previous)
    fact.update(profile=previous,attempt_id="synthetic-legacy-migration-contract",outcome="arrived")
    encoded=_canonical(fact);digest=sha256(encoded).hexdigest()
    request=payload(row)
    request["event"].update(source_id="live.infinita:native-pattern-v1:"+digest,
        byte_length=len(encoded),signature=blake2b(encoded,digest_size=8).hexdigest(),
        trail=[int.from_bytes(blake2b(str(fact[k]).encode(),digest_size=8).digest(),"big") & ((1<<63)-1)
               for k in ("context","side","outcome")])
    request["provenance"].update(profile=previous,outcome=fact,outcome_sha256=digest,
        hierarchy_id="live:patterns:"+fact["world_id"]+":nov:"+previous)
    return request

def compare(project, include_legacy_fixture=False):
    assert SDK.is_dir(), "Pinned real core required"
    sys.path.insert(0,str(SDK))
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from memoria_resolutiva.product_structural import ProductStructuralObservationService, attach_structural_observation_routes
    with tempfile.TemporaryDirectory(prefix="008eh-native-pattern-") as raw:
        tmp=pathlib.Path(raw)
        fixture,state,world,checkpoint,recall=[tmp/name for name in ("fixture.json","state.json","world.json","checkpoint.json","recall.json")]
        world.write_text(json.dumps({"world_id":"native-pattern-008eh"}))
        first,first_log=godot(project,fixture,state)
        actual=json.loads(fixture.read_text())
        assert len(actual["rows"])==4
        key="isolated-native-patterns-"+"x"*32
        def connect():
            service=ProductStructuralObservationService.open(tmp/"core",backend="sqlite",allow_fallback=False)
            app=FastAPI()
            attach_structural_observation_routes(app,api_key=key,service=service)
            return service,TestClient(app)
        service,client=connect()
        def send(payload):
            response=client.post("/api/v1/structural/observations?defer_associations=true",json=payload,headers={"X-Memoria-Key":key})
            assert response.status_code==201,response.text
            return response.json()
        def fetch():
            response=client.get("/api/v1/structural/observations/recent?limit=64",headers={"X-Memoria-Key":key})
            assert response.status_code==200,response.text
            return response.json()
        expected_count=4
        if include_legacy_fixture:
            send(legacy_contract_fixture(actual["rows"][0]))
            expected_count+=1
        intake=sync_once(fixture,world,checkpoint,recall,send=send,fetch=fetch)
        assert intake["acked"]==4 and intake["cached_recovered"]==4 and service.store.count==expected_count
        first_recovered=json.loads(recall.read_text())["entries"]
        client.close()
        del service
        service,client=connect()
        recall.unlink() # Recovery cannot rely on the export cache.
        def forbidden_send(_):
            raise AssertionError("Reopened recovery must not reingest unchanged native outcomes")
        recovery=sync_once(fixture,world,checkpoint,recall,send=forbidden_send,fetch=fetch)
        assert recovery["acked"]==0 and recovery["cached_recovered"]==4
        assert json.loads(recall.read_text())["entries"]==first_recovered
        assert service.store.count==expected_count
        client.close()
        second,second_log=godot(project,fixture,state,recall)
        baseline=next(r for r in second["runs"] if r["arm"]=="perception")
        core=next(r for r in second["runs"] if r["arm"]=="native_core_patterns")
        assert core["status"]["core_changed_initial_decisions"]==1 and core["status"]["observed_outcomes"]==1
        result={"schema":"live-infinita-native-pattern-validation/v1","sdk_commit":SDK_COMMIT,
                "core_reopened":True,"bridge_idempotent":True,"backend":"sqlite",
                "stored_recovered_events":4,
                "legacy_fixture_is_synthetic":include_legacy_fixture,
                "legacy_profile_ignored":include_legacy_fixture,
                "total_isolated_core_events":expected_count,
                "observation_ids":[r["observation_id"] for r in first_recovered],
                "intake":intake,"recovery_after_reopen_without_cache":recovery,
                "cold":first,"comparison":second,
                "core_minus_perception_distance_m":core["distance_m"]-baseline["distance_m"],
                "core_minus_perception_simulated_seconds":core["simulated_seconds"]-baseline["simulated_seconds"],
                "production_learning_demonstrated":False,
                "scope":"isolated_native_collector_and_production_bridge_with_real_core"}
        return result,first_log,second_log

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
    parser.add_argument("--output-dir",type=pathlib.Path,required=True)
    parser.add_argument("--include-legacy-fixture",action="store_true")
    args=parser.parse_args()
    result,cold,core=compare(args.project,args.include_legacy_fixture)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    for name,value in [("NATIVE_PATTERNS_RESULT_008EH.json",json.dumps(result,indent=2)+"\n"),
                       ("NATIVE_PATTERNS_COLD_008EH.txt",cold),("NATIVE_PATTERNS_CORE_008EH.txt",core)]:
        (args.output_dir/name).write_text(value)
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    main()
