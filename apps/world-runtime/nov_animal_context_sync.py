"""Store native contour approach context; collection only, no target decision authority."""
import json,time
from pathlib import Path
from hashlib import sha256
from nov_animal_approach_context import NATIVE_PROFILE,fact,payload,recover
from nov_animal_approach_sync import read_json
from nov_spatial_memory_sync import _post_local,_validate_ack,_observation_id,_world_id
from nov_navigation_memory_sync import write_checkpoint
from nov_navigation_recall_export import fetch_recent
SCHEMA="live-infinita-contextual-approach-history/v1"
RECALL_SCHEMA="live-infinita-native-contextual-approach-recall/v1"
SOURCE=Path("/var/lib/live-infinita/wildlife/search-policy.json.approach.context")
WORLD=Path("/var/lib/live-infinita/autonomous-world/world.json")
CHECKPOINT=Path("/var/lib/live-infinita/memoria-local/animal-context-checkpoint-008fg.json")
RECALL=Path("/var/lib/live-infinita/memoria-local/animal-context-recall-008fg.json")
PUBLIC=Path("/var/www/live-infinita-godot/wildlife/context-core.json")
def validate(value):
    if not isinstance(value,dict):raise ValueError("invalid_contextual_fact")
    value=dict(value)
    # Godot JSON restores integer contacts as integral floats.
    contacts=value.get("contacts")
    if type(contacts) is float and contacts.is_integer():value["contacts"]=int(contacts)
    value=fact(value)
    if value["context"]["profile"]!=NATIVE_PROFILE:raise ValueError("wrong_locomotion_profile")
    return value
def sync_once(source=SOURCE,world=WORLD,checkpoint=CHECKPOINT,recall=RECALL,public=PUBLIC,
              send=_post_local,fetch=fetch_recent,now=time.time,limit=4):
    if type(limit) is not int or not 1<=limit<=4:raise ValueError("invalid_limit")
    world_id=_world_id(world);envelope=read_json(source)
    if type(envelope.get("payload")) is not str or envelope.get("sha256")!=sha256(envelope["payload"].encode()).hexdigest():raise ValueError("invalid_checksum")
    snapshot=json.loads(envelope["payload"])
    if not isinstance(snapshot,dict) or snapshot.get("schema")!=SCHEMA or not isinstance(snapshot.get("records"),list) or len(snapshot["records"])>512:raise ValueError("invalid_snapshot")
    values=[validate(r) for r in snapshot["records"]];ids=[r["approach"]["id"] for r in values]
    if len(set(ids))!=len(ids):raise ValueError("duplicate_contextual_attempt")
    values=[r for r in values if r["approach"]["world_id"]==world_id]
    state={"schema":"live-infinita-native-contextual-approach-checkpoint/v1","world_id":world_id,"seen":{},"confirmed":0}
    if checkpoint.exists():
        old=read_json(checkpoint)
        if old.get("world_id")==world_id:
            if old.get("schema")!=state["schema"] or not isinstance(old.get("seen"),dict) or len(old["seen"])>512 or type(old.get("confirmed")) is not int or old["confirmed"]<0:raise ValueError("invalid_checkpoint")
            state=old
    state["seen"]={k:v for k,v in state["seen"].items() if k in {r["approach"]["id"] for r in values}}
    acked=0
    for value in values:
        request=payload(value);identity=_observation_id(request["event"]);attempt=value["approach"]["id"]
        if attempt in state["seen"]:
            if state["seen"][attempt]!=identity:raise ValueError("changed_contextual_attempt")
            continue
        receipt=send(request);_validate_ack(receipt,request)
        if receipt.get("backend")!="sqlite" or receipt["stored"]==receipt["duplicate"]:raise ValueError("durable_receipt_required")
        state["seen"][attempt]=identity;state["confirmed"]+=1;write_checkpoint(checkpoint,state);acked+=1
        if acked==limit:break
    entries={}
    if recall.exists():
        old=read_json(recall)
        if old.get("schema")!=RECALL_SCHEMA:raise ValueError("invalid_recall_schema")
        if old.get("world_id")==world_id:
            if not isinstance(old.get("entries"),list) or len(old["entries"])>512:raise ValueError("invalid_recall")
            for entry in old["entries"]:
                raw=dict(entry);identity=raw.pop("observation_id",None);value=validate(raw);attempt=value["approach"]["id"]
                if value["approach"]["world_id"]!=world_id or identity!=_observation_id(payload(value)["event"]) or attempt in entries:raise ValueError("invalid_cached_identity")
                entries[attempt]=dict(value,observation_id=identity)
    fetched=recover(fetch(),world_id)
    fetched=[entry for entry in fetched if entry["context"]["profile"]==NATIVE_PROFILE]
    for entry in fetched:
        attempt=entry["approach"]["id"]
        if attempt in entries and entries[attempt]!=entry:raise ValueError("conflicting_recovered_context")
        entries[attempt]=entry
    records=sorted(entries.values(),key=lambda r:(r["approach"]["ended_ms"],r["approach"]["id"]))[-512:]
    write_checkpoint(recall,{"schema":RECALL_SCHEMA,"world_id":world_id,"profile":NATIVE_PROFILE,"generated_at_unix":now(),"entries":records,"decision_use":False,"world_write_authority":False})
    result={"schema":"live-infinita-native-contextual-approach-core-status/v1","world_id":world_id,"profile":NATIVE_PROFILE,"generated_at_unix":now(),
            "source":"memoria.ia-local-structural-api","acked_this_poll":acked,"confirmed_total":state["confirmed"],"eligible_in_source":len(values),
            "recovered_this_poll":len(fetched),"cached_recovered":len(records),"decision_use":False,"world_write_authority":False,"capture":False}
    if public is not None:write_checkpoint(public,result,mode=0o644)
    return result
if __name__=="__main__":
    try:print(json.dumps(sync_once(),sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__}));raise SystemExit(1)
