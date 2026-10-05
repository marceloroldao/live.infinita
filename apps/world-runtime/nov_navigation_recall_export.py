"""Export bounded navigation evidence retrieved from local Memoria.ia."""
from __future__ import annotations
import json
import math
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
PANEL=Path("/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-learning-status-008df.json")

def fetch_recent() -> dict:
    key=os.environ.get("MEMORIA_API_KEY","")
    if len(key)<32:
        raise NavigationSyncError("local_api_key_unconfigured")
    # Core recent() samples count before ordered_from(); concurrent intake can
    # add rows between those reads. Leave bounded headroom and retry overflow.
    req=Request("http://127.0.0.1:8788/api/v1/structural/observations/recent?limit=64",
                headers={"X-Memoria-Key":key,"Accept":"application/json"})
    for attempt in range(2):
        with build_opener(ProxyHandler({})).open(req,timeout=15) as response:
            raw=response.read(2_000_001)
            if response.status!=200 or len(raw)>2_000_000:
                raise NavigationSyncError("recall_response_invalid")
        data=json.loads(raw)
        if not isinstance(data,dict) or data.get("semantic_projection") is not False or not isinstance(data.get("items"),list):
            raise NavigationSyncError("recall_contract_invalid")
        if len(data["items"])<=100:
            return data
    raise NavigationSyncError("recall_window_raced_after_retry")

def export_once(world: Path=WORLD, private: Path=PRIVATE, public: Path=PUBLIC, fetch=fetch_recent, now=time.time, panel_source: Path=PANEL) -> dict:
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
    panel=read_learning_status(panel_source,world_id,now())
    if panel is not None:
        result["learning_status"]=panel
    if len(_canonical(result))>2_000_000:
        raise NavigationSyncError("recall_export_oversized")
    write_checkpoint(private,result)
    write_checkpoint(public,result,mode=0o644)
    return {"recovered":recovered,"cached":len(rows),"source":result["source"]}

def read_learning_status(path: Path,world_id: str,now: float) -> dict | None:
    try:
        if path.is_symlink() or not path.exists() or path.stat().st_size>12000:
            return None
        value=json.loads(path.read_text())
        if not isinstance(value,dict) or value.get("schema")!="live-infinita-nov-learning-status/v1" or value.get("world_id")!=world_id:
            return None
        stamp=value.get("observed_at_unix")
        if not isinstance(stamp,(float,int)) or isinstance(stamp,bool) or not 0<=now-stamp<=60:
            return None
        fields=("arrivals","interruptions","blocked_attempts","completed_steps","causal_ram_steps","causal_memoria_steps")
        if any(not isinstance(value.get(k),(int,float)) or isinstance(value[k],bool) or not 0<=value[k]<=1e9 or value[k]!=int(value[k]) for k in fields):
            return None
        distance=value.get("distance_m",0.0)
        if not isinstance(distance,(int,float)) or isinstance(distance,bool) or not math.isfinite(distance) or not 0<=distance<=1e7:
            return None
        active=value.get("active",False)
        if not isinstance(active,bool):
            return None
        state=value.get("motion_state","walking" if active else "idle")
        if state not in ("idle","walking","no_passage","water_egress"):
            return None
        return {"motion_state":state,"last_reason":str(value.get("last_reason",""))[:80],"distance_m":distance,"active":active,**{k:int(value[k]) for k in fields},"observed_at_unix":stamp,"result":str(value.get("result",""))[:120],
            "source":"native_renderer_journey","world_id":world_id}
    except (OSError,ValueError,TypeError):
        return None
