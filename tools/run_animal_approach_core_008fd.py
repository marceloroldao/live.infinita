#!/usr/bin/env python3
"""Replay published real production outcomes into an isolated SQLite core and reopen it."""
import argparse,json,pathlib,sys,tempfile,urllib.request,time
from hashlib import sha256
from run_physical_memory_comparison_008ed import SDK,SDK_COMMIT
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"));sys.path.insert(0,str(SDK))
from nov_animal_approach_sync import SCHEMA,sync_once,payload
from memoria_resolutiva.product_structural import ProductStructuralObservationService,attach_structural_observation_routes
from fastapi import FastAPI
from fastapi.testclient import TestClient
p=argparse.ArgumentParser(description=__doc__);p.add_argument("--output-dir",type=pathlib.Path,required=True);a=p.parse_args()
a.output_dir.mkdir(parents=True,exist_ok=True)
live=json.load(urllib.request.urlopen("https://live.etbra.com.br/godot/wildlife/search-intent.json?t="+str(time.time()),timeout=20))
assert live["last_error"] is None and live["approach"]["history"]["persistent"]
rows=live["approach"]["results"]
assert rows and len(rows)<=16
(a.output_dir/"production_public_outcomes.json").write_text(json.dumps(live["approach"],indent=2)+"\n")
with tempfile.TemporaryDirectory(prefix="008fd-isolated-core-") as folder:
    tmp=pathlib.Path(folder);source,world,checkpoint,recall=[tmp/n for n in ("source","world","checkpoint","recall")]
    # Serialization adapter only: measurements come unchanged from the native public mirror.
    raw=json.dumps({"schema":SCHEMA,"records":rows,"pending":{}})
    source.write_text(json.dumps({"payload":raw,"sha256":sha256(raw.encode()).hexdigest()}))
    world.write_text(json.dumps({"world_id":live["world_id"]}))
    key="isolated-approach-"+("x"*32)
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
    batches=[]
    for _ in range(5):
        d=sync_once(source,world,checkpoint,recall,None,send=send,fetch=fetch);batches.append(d)
        if d["acked_this_poll"]==0:break
    expected=json.loads(recall.read_text())["entries"]
    eligible=[r for r in rows if r["learning_eligible"]]
    assert len(expected)==service.store.count==len(eligible)>0
    assert all(not e["censored"] and not e["capture"] for e in expected)
    client.close();client=None;service=None
    service,client=connect();recall.unlink()
    def forbidden(_):raise AssertionError("Cold recovery must not substitute reingestion")
    cold=sync_once(source,world,checkpoint,recall,None,send=forbidden,fetch=fetch)
    assert cold["acked_this_poll"]==0 and cold["cached_recovered"]==len(expected)
    assert json.loads(recall.read_text())["entries"]==expected and service.store.count==len(expected)
    client.close()
    (a.output_dir/"cold_recovered_outcomes.json").write_text(json.dumps(expected,indent=2)+"\n")
    report={"schema":"live-infinita-animal-approach-core-validation/v1","sdk_commit":SDK_COMMIT,"backend":"sqlite","allow_fallback":False,
            "source":"unchanged real native outcomes from production public mirror; sealed serialization adapter in isolate",
            "stored_actual_outcomes":len(expected),"batches":batches,"cold_recovery":cold,"production_core_changed":False,
            "decision_use":False,"learned_hunting":False,"benefit_demonstrated":False}
    (a.output_dir/"CORE_VALIDATION_008FD.json").write_text(json.dumps(report,indent=2)+"\n")
    print("008FD_REAL_CORE_COLD_RECOVERY_PASS facts="+str(len(expected)))
