"""Export bounded navigation evidence retrieved from local Memoria.ia."""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
from urllib.request import Request,ProxyHandler,build_opener
from nov_navigation_memory_sync import WORLD,NavigationSyncError,point,_world_id,write_checkpoint,_canonical
from nov_spatial_memory_sync import _observation_id
SCHEMA="live-infinita-nov-navigation-recall/v1"
PRIVATE=Path("/var/lib/live-infinita/memoria-local/navigation-recall.json")
PUBLIC=Path("/var/www/live-infinita-godot/navigation-memory/recall.json")
LIMIT=4096

def fetch_recent() -> dict:
    key=os.environ.get("MEMORIA_API_KEY","")
    if len(key)<32:
        raise NavigationSyncError("local_api_key_unconfigured")
    req=Request("http://127.0.0.1:8788/api/v1/structural/observations/recent?limit=100",
                headers={"X-Memoria-Key":key,"Accept":"application/json"})
    with build_opener(ProxyHandler({})).open(req,timeout=15) as response:
        raw=response.read(2_000_001)
        if response.status!=200 or len(raw)>2_000_000:
            raise NavigationSyncError("recall_response_invalid")
    return json.loads(raw)

def export_once(world: Path=WORLD, private: Path=PRIVATE, public: Path=PUBLIC, fetch=fetch_recent, now=time.time) -> dict:
    world_id=_world_id(world)
    response=fetch()
    if not isinstance(response,dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"),list) or len(response["items"])>100:
        raise NavigationSyncError("recall_contract_invalid")
    entries={}
    if private.exists():
        if private.is_symlink() or private.stat().st_size>2_000_000:
            raise NavigationSyncError("recall_cache_invalid")
        old=json.loads(private.read_text())
        if old.get("schema")==SCHEMA and old.get("world_id")==world_id:
            rows=old.get("entries",[])
            if not isinstance(rows,list) or len(rows)>LIMIT:
                raise NavigationSyncError("recall_cache_limit")
            entries={i["kind"]+":"+i["key"]:i for i in rows}
    recovered=0
    # oldest first: latest count/route replaces earlier evidence for same item.
    for envelope in response["items"]:
        if not isinstance(envelope,dict):
            raise NavigationSyncError("recall_envelope_invalid")
        provenance=envelope.get("provenance",{})
        if provenance.get("hierarchy_id")!=f"live:navigation:{world_id}:nov:renderer" or provenance.get("source_kind")!="native_renderer_navigation_summary":
            continue
        if provenance.get("world_write_authority") is not False or provenance.get("chronological_episode") is not False:
            raise NavigationSyncError("recall_provenance_invalid")
        event=envelope.get("event",{})
        observation_id=envelope.get("observation_id")
        if observation_id!=_observation_id(event):
            raise NavigationSyncError("recall_identity_invalid")
        item=provenance.get("summary",{})
        kind=item.get("kind")
        key=item.get("key","")
        if kind=="blocked_passage":
            start,end=key.split(">")
            point(start);point(end)
            if type(item.get("observed_count")) is not int or not 1<=item["observed_count"]<=100:
                raise NavigationSyncError("recall_count_invalid")
        elif kind=="successful_route_step":
            goal,start=key.split("|")
            point(goal);point(start)
            end=item.get("to",[])
            if not isinstance(end,list) or len(end)!=2:
                raise NavigationSyncError("recall_route_invalid")
            point(",".join(str(v) for v in end))
        else:
            raise NavigationSyncError("recall_kind_invalid")
        row={**item,"observation_id":observation_id}
        entries[kind+":"+key]=row
        recovered+=1
    rows=list(entries.values())[-LIMIT:]
    result={"schema":SCHEMA,"world_id":world_id,"generated_at_unix":now(),"expires_after_seconds":180,
            "source":"memoria.ia-local-structural-api","coordinate_space":"godot-renderer-xz-metres",
            "world_write_authority":False,"entries":rows}
    if len(_canonical(result))>2_000_000:
        raise NavigationSyncError("recall_export_oversized")
    write_checkpoint(private,result)
    write_checkpoint(public,result)
    os.chmod(public,0o644)
    return {"recovered":recovered,"cached":len(rows),"source":result["source"]}
