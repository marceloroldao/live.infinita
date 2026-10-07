"""Durably ingest ONLY Nov eye-sensor encounters into the frozen structural API.

The global animal rendering projection is never read. One immutable encounter is
posted and recovered before its outbox sequence is acknowledged. No decisions.
"""
from hashlib import blake2b, sha256
import json
import math
from pathlib import Path
import re
import time
from nov_spatial_memory_sync import _canonical, _validate_ack, _observation_id, _world_id
from nov_navigation_memory_sync import write_checkpoint
from world_weather_memory_experiment import request_api

SOURCE = Path("/var/lib/live-infinita/wildlife/encounters.json")
ACK = Path("/var/lib/live-infinita/wildlife/encounters-ack.json")
PUBLIC = Path("/var/www/live-infinita-godot/wildlife/encounter-memory.json")
WORLD = Path("/var/lib/live-infinita/autonomous-world/world.json")
SCHEMA = "live-infinita-nov-animal-encounters/v1"
ACK_SCHEMA = "live-infinita-nov-animal-memory-ack/v1"
STATUS_SCHEMA = "live-infinita-nov-animal-memory/v1"
MAX_BYTES = 1000000


def number(v, low, high):
    if type(v) not in (int,float) or not math.isfinite(v) or not low <= v <= high:
        raise ValueError("animal_memory_number")
    return v


def integer(v, low=0, high=10**15):
    number(v, low, high)
    if v != int(v): raise ValueError("animal_memory_integer")
    return int(v)


def point(v):
    if not isinstance(v,list) or len(v)!=3: raise ValueError("animal_memory_point")
    for n in v:number(n,-100000,100000)
    return v


def validate_record(row, world_id):
    if not isinstance(row,dict) or set(row)!={"sequence","entity_id","kind","first_seen_ms","last_seen_ms","first_observer_eye_m","last_observer_eye_m","first_target_m","last_target_m","sample_count","min_distance_m","max_distance_m","first_range_m","last_range_m","closed_reason"}:
        raise ValueError("animal_memory_record_fields")
    integer(row["sequence"],1)
    if row["kind"]!="rabbit" or not isinstance(row["entity_id"],str) or not row["entity_id"].startswith(world_id+":rabbit:") or len(row["entity_id"])>200:
        raise ValueError("animal_memory_entity")
    first=integer(row["first_seen_ms"]);last=integer(row["last_seen_ms"])
    if not first<=last<first+30000: raise ValueError("animal_memory_duration")
    count=integer(row["sample_count"],1,200)
    if count>1 and last==first:raise ValueError("animal_memory_replayed_sample")
    low=number(row["min_distance_m"],0.05,24)
    high=number(row["max_distance_m"],low,24)
    for prefix in ("first","last"):
        eye=point(row[prefix+"_observer_eye_m"]);target=point(row[prefix+"_target_m"])
        reach=number(row[prefix+"_range_m"],12,24)
        distance=math.dist(eye,target)
        if not low-0.01<=distance<=high+0.01 or distance>reach+0.01:raise ValueError("animal_memory_sensor_geometry")
    if row["closed_reason"] not in ("lost_visual_contact","window_complete","renderer_restart"):
        raise ValueError("animal_memory_closed_reason")
    return row


def read_source(path, world_id, now=None):
    if path.is_symlink():raise ValueError("animal_memory_source_symlink")
    raw=path.read_bytes()
    if len(raw)>MAX_BYTES:raise ValueError("animal_memory_source_budget")
    envelope=json.loads(raw)
    if not isinstance(envelope,dict) or not isinstance(envelope.get("payload"),str) or envelope.get("sha256")!=sha256(envelope["payload"].encode()).hexdigest():
        raise ValueError("animal_memory_source_checksum")
    value=json.loads(envelope["payload"])
    if not isinstance(value,dict) or value.get("schema")!=SCHEMA or value.get("world_id")!=world_id or value.get("source")!="local_physics_eye_sensor" or value.get("world_write_authority") is not False or value.get("contains_prediction") is not False or value.get("absence_claim") is not False:
        raise ValueError("animal_memory_source_identity")
    if not isinstance(value.get("session_id"),str) or not re.fullmatch("[0-9a-f]{32}",value["session_id"]):raise ValueError("animal_memory_session")
    stamp=number(value.get("generated_at_unix"),0,10**12)
    if not -30<=(time.time() if now is None else now)-stamp<=180:raise ValueError("animal_memory_source_stale")
    logical=integer(value.get("logical_time_ms"))
    cursor=integer(value.get("acknowledged_sequence"));next_seq=integer(value.get("next_sequence"),1)
    if cursor>=next_seq:raise ValueError("animal_memory_source_cursor")
    rows=value.get("pending")
    if not isinstance(rows,list) or len(rows)>128:raise ValueError("animal_memory_source_pending")
    sequence=cursor
    for row in rows:
        validate_record(row,world_id)
        sequence+=1
        if row["sequence"]!=sequence or row["last_seen_ms"]>logical:raise ValueError("animal_memory_source_sequence")
    if sequence!=next_seq-1:raise ValueError("animal_memory_source_gap")
    if not isinstance(value.get("active"),dict) or len(value["active"])>16:raise ValueError("animal_memory_active_budget")
    integer(value.get("dropped_samples"))
    return value


def payload(world_id, session, row):
    validate_record(row,world_id)
    # Godot JSON reloads integers as floats. Canonicalize all numeric fields so
    # renderer restart cannot change the immutable event identity.
    row=dict(row)
    for key in ("sequence","first_seen_ms","last_seen_ms","sample_count"):row[key]=int(row[key])
    for key in ("min_distance_m","max_distance_m","first_range_m","last_range_m"):row[key]=float(row[key])
    for key in ("first_observer_eye_m","last_observer_eye_m","first_target_m","last_target_m"):row[key]=[float(n) for n in row[key]]
    raw=_canonical(row)
    def symbol(position, stamp):
        return int.from_bytes(blake2b(_canonical({"cell":[math.floor(position[0]/4),math.floor(position[2]/4)],"day_bin":int(stamp%3600000//300000),"kind":"rabbit"}),digest_size=8).digest(),"big")
    event={"version":1,"source_id":f"live.infinita:{world_id}:nov:eye-encounter:{session}","sequence":int(row["sequence"]),"byte_offset":0,"byte_length":len(raw),"trail":[symbol(row["first_target_m"],row["first_seen_ms"]),symbol(row["last_target_m"],row["last_seen_ms"])],"relation_ids":[],"signature":blake2b(raw,digest_size=8).hexdigest(),"resolution":1}
    return {"event":event,"provenance":{"hierarchy_id":f"live:animal-encounter:{world_id}:nov:eye","source_kind":"observed_animal_encounter","world_id":world_id,"entity_id":"nov","observation_channel":"local_physics_eye_sensor","session_id":session,"encounter":row,"payload_sha256":sha256(raw).hexdigest(),"world_write_authority":False,"selection_authority":False,"contains_prediction":False,"absence_claim":False,"recognition":"registered_instance_label_not_learned_visual_identity"}}


def seal_ack(value):
    proof={k:v for k,v in value.items() if k not in ("proof_payload","checksum")}
    encoded=_canonical(proof).decode()
    return {**proof,"proof_payload":encoded,"checksum":sha256(encoded.encode()).hexdigest()}


def read_ack(path, source):
    if not path.exists() and source["acknowledged_sequence"]!=0:raise ValueError("animal_memory_ack_missing")
    if not path.exists():return {"schema":ACK_SCHEMA,"world_id":source["world_id"],"session_id":source["session_id"],"cursor":0,"last_observation_id":None,"verified_history":[]}
    if path.is_symlink():raise ValueError("animal_memory_ack_symlink")
    value=json.loads(path.read_text())
    if value!=seal_ack(value) or value.get("schema")!=ACK_SCHEMA or value.get("world_id")!=source["world_id"] or value.get("session_id")!=source["session_id"]:
        raise ValueError("animal_memory_ack_identity")
    cursor=integer(value.get("cursor"))
    if not source["acknowledged_sequence"]<=cursor<source["next_sequence"]:raise ValueError("animal_memory_ack_cursor")
    if not isinstance(value.get("verified_history"),list) or len(value["verified_history"])>16:raise ValueError("animal_memory_ack_budget")
    return value


def verify_recall(response, expected):
    if not isinstance(response,dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"),list) or len(response["items"])>100:
        raise ValueError("animal_memory_recall_contract")
    identity=_observation_id(expected["event"])
    for item in response["items"]:
        if isinstance(item,dict) and item.get("observation_id")==identity:
            if item.get("event")!=expected["event"] or item.get("provenance")!=expected["provenance"]:
                raise ValueError("animal_memory_recall_content")
            return item
    raise ValueError("animal_memory_recall_not_found")


def sync_once(source=SOURCE, ack=ACK, public=PUBLIC, world=WORLD, api=request_api):
    expected_world=_world_id(world)
    status={"schema":STATUS_SCHEMA,"world_id":expected_world,"generated_at_unix":time.time(),"world_write_authority":False,"decision_use":False,"learning_improvement_measured":False,"stored_and_recovered_encounters":0,"pending":0,"active_encounters":0,"last_observation_id":None,"last_error":None}
    if not source.exists():
        status["reason"]="waiting_for_eye_sensor";write_checkpoint(public,status,0o644);return status
    s=read_source(source,expected_world);a=read_ack(ack,s)
    candidates=[r for r in s["pending"] if r["sequence"]>a["cursor"]]
    if candidates:
        row=candidates[0]
        if row["sequence"]!=a["cursor"]+1:raise ValueError("animal_memory_ack_gap")
        expected=payload(expected_world,s["session_id"],row)
        reply=api("/api/v1/structural/observations?defer_associations=true",expected)
        _validate_ack(reply,expected)
        if reply.get("stored") is not True and reply.get("duplicate") is not True:raise ValueError("animal_memory_unstored_ack")
        recovered=verify_recall(api("/api/v1/structural/observations/recent?limit=100"),expected)
        a["cursor"]=int(row["sequence"]);a["last_observation_id"]=recovered["observation_id"]
        a["verified_history"]=(a["verified_history"]+[{"observation_id":recovered["observation_id"],"encounter":row,"verified_at_unix":time.time()}])[-16:]
    elif time.time()-a.get("api_checked_at_unix",0)>=60:
        response=api("/api/v1/structural/observations/recent?limit=100")
        if response.get("semantic_projection") is not False or not isinstance(response.get("items"),list):raise ValueError("animal_memory_recall_contract")
    if candidates or time.time()-a.get("api_checked_at_unix",0)>=60:a["api_checked_at_unix"]=time.time()
    write_checkpoint(ack,seal_ack(a))
    status.update(stored_and_recovered_encounters=a["cursor"],pending=sum(r["sequence"]>a["cursor"] for r in s["pending"]),active_encounters=len(s.get("active",{})),last_observation_id=a["last_observation_id"],dropped_samples=s["dropped_samples"],reason="stored_and_recovered" if candidates else "waiting_for_completed_encounter",verified_history=a["verified_history"])
    write_checkpoint(public,status,0o644)
    return status


def main():
    try:result=sync_once()
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) and str(exc).startswith("animal_memory_") else "animal_memory_api_or_contract_unavailable"
        result={"schema":STATUS_SCHEMA,"generated_at_unix":time.time(),"last_error":code,"reason":"retry_pending_preserved","world_write_authority":False,"decision_use":False,"learning_improvement_measured":False}
        write_checkpoint(PUBLIC,result,0o644)
    print(json.dumps({k:v for k,v in result.items() if k not in ("verified_history",)},sort_keys=True))

if __name__=="__main__":main()
