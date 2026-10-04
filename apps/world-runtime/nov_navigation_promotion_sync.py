"""Promote bounded, causally reused RAM experiences to local Memoria.ia."""
from nov_navigation_episode_sync import integer
from hashlib import blake2b
import json
from pathlib import Path
import re
from nov_navigation_memory_sync import payload as summary_payload, write_checkpoint, point
from nov_spatial_memory_sync import _canonical, _world_id, _post_local, _validate_ack, _observation_id

SOURCE = Path("/opt/live.infinita/.local/share/godot/app_userdata/Live Infinita Showcase/nov-navigation-promotions-008ci.json")
WORLD = Path("/var/lib/live-infinita/autonomous-world/world.json")
CHECKPOINT = Path("/var/lib/live-infinita/memoria-local/navigation-promotions.checkpoint.json")
SCHEMA = "live-infinita-nov-navigation-promotions/v1"
CP_SCHEMA = "live-infinita-nov-navigation-promotion-checkpoint/v1"

def read_source(source, world_id):
    if source.is_symlink():
        raise ValueError("promotion_source_symlink")
    with source.open("rb") as f:
        raw=f.read(2_000_001)
    if len(raw)>2_000_000:
        raise ValueError("promotion_source_oversized")
    data=json.loads(raw)
    if (not isinstance(data,dict) or data.get("schema")!=SCHEMA or
        data.get("source")!="native_renderer_working_memory" or data.get("world_write_authority") is not False):
        raise ValueError("promotion_contract_invalid")
    if data.get("world_id")!=world_id:
        return [] # Old context cannot be attached to the current world.
    rows=data.get("entries")
    if not isinstance(rows,list) or len(rows)>512:
        raise ValueError("promotion_limit")
    keys=set()
    for row in rows:
        if not isinstance(row,dict):
            raise ValueError("promotion_support_invalid")
        row["successful_causal_reuses"] = integer(row.get("successful_causal_reuses"), 3, 3)
        if row["successful_causal_reuses"]!=3:
            raise ValueError("promotion_support_invalid")
        ids=row.get("decision_ids")
        if (not isinstance(ids,list) or len(ids)!=3 or
            any(not isinstance(i,str) or not re.fullmatch("[0-9a-f]{32}:[1-9][0-9]*",i) for i in ids) or len(set(ids))!=3):
            raise ValueError("promotion_decisions_invalid")
        if len({i.split(":")[0] for i in ids})!=1:
            raise ValueError("promotion_session_invalid")
        item=row.get("summary")
        if not isinstance(item,dict) or item.get("kind")!="successful_route_step":
            raise ValueError("promotion_summary_invalid")
        item["observed_count"] = integer(item.get("observed_count"), 1, 1)
        key=item.get("key","")
        if not re.fullmatch(r"-?\d+,-?\d+\|-?\d+,-?\d+",key) or key in keys:
            raise ValueError("promotion_address_invalid")
        keys.add(key)
        goal,start=key.split("|")
        if item.get("from")!=point(start) or item.get("goal")!=point(goal):
            raise ValueError("promotion_coordinate_identity")
        end=item.get("to")
        if not isinstance(end,list) or len(end)!=2:
            raise ValueError("promotion_coordinate_invalid")
        point(",".join(str(v) for v in end))
    return rows

def payload(row, world_id):
    item=row["summary"]
    value=summary_payload(item,world_id,"")
    signature=blake2b(_canonical(row),digest_size=8).hexdigest()
    value["event"]["source_id"]=f"live.infinita:{world_id}:nov:working-memory-promotion:"+blake2b(item["key"].encode(),digest_size=16).hexdigest()
    value["event"]["signature"]=signature
    value["provenance"]["learning_source"]="native_renderer_working_memory"
    value["provenance"]["world_id_role"]="recorded_world_feed_context"
    value["provenance"]["promotion"]={"successful_causal_reuses":3,"decision_ids":row["decision_ids"]}
    return value

def sync_once(source=SOURCE, world=WORLD, checkpoint=CHECKPOINT, send=_post_local, limit=2):
    if type(limit) is not int or not 1<=limit<=2:
        raise ValueError("promotion_limit_invalid")
    if not source.exists():
        return {"status":"awaiting_ram_promotions","acked":0}
    world_id=_world_id(world)
    rows=read_source(source,world_id)
    state={"schema":CP_SCHEMA,"seen":{},"confirmed":0}
    if checkpoint.is_symlink():
        raise ValueError("promotion_checkpoint_symlink")
    if checkpoint.exists():
        if checkpoint.stat().st_size>2_000_000:
            raise ValueError("promotion_checkpoint_oversized")
        state=json.loads(checkpoint.read_text())
        if (not isinstance(state,dict) or state.get("schema")!=CP_SCHEMA or
            not isinstance(state.get("seen"),dict) or len(state["seen"])>4096 or
            type(state.get("confirmed")) is not int or state["confirmed"]<0):
            raise ValueError("promotion_checkpoint_invalid")
        for key,value in state["seen"].items():
            if not re.fullmatch("[0-9a-f]{32}",key) or not re.fullmatch("structural-event:[0-9a-f]{40}",str(value)):
                raise ValueError("promotion_checkpoint_identity")
    acked=0
    for row in rows:
        value=payload(row,world_id)
        expected=_observation_id(value["event"])
        identity=blake2b(_canonical({"world_id":world_id,"key":row["summary"]["key"]}),digest_size=16).hexdigest()
        if state["seen"].get(identity)==expected:
            continue
        receipt=send(value)
        _validate_ack(receipt,value)
        if receipt["stored"]==receipt["duplicate"]:
            raise ValueError("promotion_ack_invalid")
        state["seen"][identity]=expected
        while len(state["seen"])>4096:
            del state["seen"][next(iter(state["seen"]))]
        state["confirmed"]+=1
        state["last_observation_id"]=expected
        write_checkpoint(checkpoint,state)
        acked+=1
        if acked>=limit:
            break
    return {"status":"ok","acked":acked,"confirmed":state["confirmed"],"eligible":len(rows),"source":"ram_promotions","world_mutated":False}
