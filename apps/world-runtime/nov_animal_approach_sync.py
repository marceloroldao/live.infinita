"""Mirror measured approach outcomes into structural memory; never steer the world."""
from hashlib import blake2b, sha256
import json
import math
from pathlib import Path
import time
from nov_spatial_memory_sync import _canonical, _post_local, _validate_ack, _observation_id, _world_id
from nov_navigation_memory_sync import write_checkpoint
from nov_navigation_recall_export import fetch_recent
SCHEMA="live-infinita-animal-approach-history/v1"
RECALL_SCHEMA="live-infinita-animal-approach-recall/v1"
KIND="native_observed_animal_approach_outcome"
LIMIT=512
SOURCE=Path("/var/lib/live-infinita/wildlife/search-policy.json.approach")
WORLD=Path("/var/lib/live-infinita/autonomous-world/world.json")
CHECKPOINT=Path("/var/lib/live-infinita/memoria-local/animal-approach-checkpoint-008fd.json")
RECALL=Path("/var/lib/live-infinita/memoria-local/animal-approach-recall-008fd.json")
PUBLIC=Path("/var/www/live-infinita-godot/wildlife/approach-core.json")
OUTCOMES={"approached","contact_lost","no_progress","budget_exhausted"}
CENSORED={"destination_rejected","clock_unavailable","feed_unavailable","world_changed","clock_rewind","navigation_recovery","renderer_restart","test_interrupted"}
FIELDS={"id","world_id","entity_id","started_ms","ended_ms","result","distance_m","initial_observed_remaining_m",
        "final_observed_remaining_m","revision","censored","learning_eligible","capture","contains_prediction","absence_claim","world_write_authority"}
PENDING_FIELDS=FIELDS-{"final_observed_remaining_m","revision"}
class ApproachSyncError(RuntimeError): pass
def read_json(path):
    if path.is_symlink() or path.stat().st_size>1_000_000:raise ApproachSyncError("invalid_bounded_file")
    value=json.loads(path.read_text())
    if not isinstance(value,dict):raise ApproachSyncError("invalid_document")
    return value
def number(value,integer=False):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1e15 and (not integer or value==int(value))
def validate(value):
    if not isinstance(value,dict) or set(value) not in (FIELDS,PENDING_FIELDS):raise ApproachSyncError("invalid_fields")
    r=dict(value)
    world=r["world_id"]
    if not isinstance(world,str) or not 1<=len(world)<=160:raise ApproachSyncError("invalid_world")
    for key,prefix,bound in (("id",world+":animal-approach:",240),("entity_id",world+":rabbit:",160)):
        if not isinstance(r[key],str) or not r[key].startswith(prefix) or not len(prefix)<len(r[key])<=bound:raise ApproachSyncError("invalid_identity")
    for key in ("capture","contains_prediction","absence_claim","world_write_authority"):
        if r[key] is not False:raise ApproachSyncError("non_fact_marker")
    if type(r["censored"]) is not bool or type(r["learning_eligible"]) is not bool:raise ApproachSyncError("invalid_eligibility")
    if r["result"] not in OUTCOMES|CENSORED or r["censored"]!=(r["result"] in CENSORED):raise ApproachSyncError("invalid_result")
    if not number(r["started_ms"],True) or not number(r["initial_observed_remaining_m"]):raise ApproachSyncError("invalid_start")
    r["started_ms"]=int(r["started_ms"]);r["initial_observed_remaining_m"]=float(r["initial_observed_remaining_m"])
    if r["ended_ms"] is None or r["distance_m"] is None:
        if set(r)!=PENDING_FIELDS or r["result"]!="renderer_restart" or r["ended_ms"] is not None or r["distance_m"] is not None or r["learning_eligible"]:raise ApproachSyncError("invalid_interruption")
        return r
    if set(r)!=FIELDS or not number(r["ended_ms"],True) or r["ended_ms"]<r["started_ms"]:raise ApproachSyncError("invalid_end")
    if not number(r["distance_m"]) or not number(r["final_observed_remaining_m"]) or not number(r["revision"],True):raise ApproachSyncError("invalid_measurement")
    r["ended_ms"]=int(r["ended_ms"]);r["revision"]=int(r["revision"])
    r["distance_m"]=float(r["distance_m"]);r["final_observed_remaining_m"]=float(r["final_observed_remaining_m"])
    if r["result"]=="approached" and r["final_observed_remaining_m"]>6.5:raise ApproachSyncError("unconfirmed_proximity")
    if r["learning_eligible"]!=(not r["censored"] and r["distance_m"]>0):raise ApproachSyncError("invalid_eligibility")
    return r
def payload(row):
    row=validate(row)
    if not row["learning_eligible"]:raise ApproachSyncError("ineligible_outcome")
    raw=_canonical(row);digest=sha256(raw).hexdigest()
    event={"version":1,"source_id":"live.infinita:observed-approach-v1:"+digest,"sequence":1,"byte_offset":0,"byte_length":len(raw),
           "trail":[int.from_bytes(blake2b(str(row[k]).encode(),digest_size=8).digest(),"big")&((1<<63)-1) for k in ("world_id","entity_id","result")],
           "relation_ids":[1],"signature":blake2b(raw,digest_size=8).hexdigest(),"resolution":1}
    return {"event":event,"provenance":{"hierarchy_id":"live:animal-approaches:"+row["world_id"]+":nov",
            "source_kind":KIND,"world_id":row["world_id"],"entity_id":"nov","world_write_authority":False,
            "contains_prediction":False,"outcome_sha256":digest,"outcome":row}}
def sync_once(source=SOURCE,world=WORLD,checkpoint=CHECKPOINT,recall=RECALL,public=PUBLIC,
              send=_post_local,fetch=fetch_recent,now=time.time,limit=4):
    if type(limit) is not int or not 1<=limit<=4:raise ApproachSyncError("invalid_limit")
    world_id=_world_id(world)
    sealed=read_json(source)
    if type(sealed.get("payload")) is not str or sealed.get("sha256")!=sha256(sealed["payload"].encode()).hexdigest():raise ApproachSyncError("invalid_checksum")
    snapshot=json.loads(sealed["payload"])
    if not isinstance(snapshot,dict) or snapshot.get("schema")!=SCHEMA or not isinstance(snapshot.get("records"),list) or len(snapshot["records"])>LIMIT or not isinstance(snapshot.get("pending"),dict):raise ApproachSyncError("invalid_snapshot")
    if snapshot["pending"]:
        pending=validate(snapshot["pending"])
        if pending["result"]!="renderer_restart":raise ApproachSyncError("invalid_pending")
    rows=[validate(row) for row in snapshot["records"]]
    ids=[r["id"] for r in rows]
    if len(set(ids))!=len(ids) or snapshot["pending"].get("id") in ids:raise ApproachSyncError("duplicate_attempt")
    scoped=[r for r in rows if r["world_id"]==world_id]
    eligible=[r for r in scoped if r["learning_eligible"]]
    state={"schema":"live-infinita-animal-approach-checkpoint/v1","world_id":world_id,"seen":{},"confirmed":0}
    if checkpoint.exists():
        old=read_json(checkpoint)
        if old.get("world_id")==world_id:
            if old.get("schema")!=state["schema"] or not isinstance(old.get("seen"),dict) or len(old["seen"])>LIMIT or type(old.get("confirmed")) is not int or old["confirmed"]<0:raise ApproachSyncError("invalid_checkpoint")
            state=old
    state["seen"]={k:v for k,v in state["seen"].items() if k in {r["id"] for r in eligible}}
    acked=0
    for row in eligible:
        request=payload(row);expected=_observation_id(request["event"])
        prior=state["seen"].get(row["id"])
        if prior is not None:
            if prior!=expected:raise ApproachSyncError("changed_attempt")
            continue
        receipt=send(request);_validate_ack(receipt,request)
        if receipt.get("backend")!="sqlite" or receipt["stored"]==receipt["duplicate"]:raise ApproachSyncError("durable_receipt_required")
        state["seen"][row["id"]]=expected;state["confirmed"]+=1
        write_checkpoint(checkpoint,state);acked+=1
        if acked==limit:break
    response=fetch()
    if not isinstance(response,dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"),list) or len(response["items"])>100:raise ApproachSyncError("invalid_recovery")
    recovered={}
    if recall.exists():
        old=read_json(recall)
        if old.get("schema")!=RECALL_SCHEMA:raise ApproachSyncError("invalid_recall_schema")
        if old.get("world_id")==world_id:
            if not isinstance(old.get("entries"),list) or len(old["entries"])>LIMIT:raise ApproachSyncError("invalid_cache")
            for entry in old["entries"]:
                fact=dict(entry);identity=fact.pop("observation_id",None);fact=validate(fact)
                if fact["world_id"]!=world_id or identity!=_observation_id(payload(fact)["event"]) or fact["id"] in recovered:raise ApproachSyncError("invalid_cached_identity")
                recovered[fact["id"]]=dict(fact,observation_id=identity)
    fetched=0
    for envelope in response["items"]:
        if not isinstance(envelope,dict):raise ApproachSyncError("invalid_envelope")
        provenance=envelope.get("provenance",{})
        if not isinstance(provenance,dict):raise ApproachSyncError("invalid_provenance")
        if provenance.get("source_kind")!=KIND or provenance.get("world_id")!=world_id:continue
        fact=validate(provenance.get("outcome"));expected=payload(fact)
        if _canonical(envelope.get("event"))!=_canonical(expected["event"]) or _canonical(provenance)!=_canonical(expected["provenance"]) or envelope.get("observation_id")!=_observation_id(expected["event"]):raise ApproachSyncError("recovered_fact_mismatch")
        entry=dict(fact,observation_id=envelope["observation_id"])
        if fact["id"] in recovered and recovered[fact["id"]]!=entry:raise ApproachSyncError("conflicting_recovered_attempt")
        recovered[fact["id"]]=entry;fetched+=1
    entries=sorted(recovered.values(),key=lambda r:(r["ended_ms"],r["id"]))[-LIMIT:]
    write_checkpoint(recall,{"schema":RECALL_SCHEMA,"world_id":world_id,"generated_at_unix":now(),"source":"memoria.ia-local-structural-api","world_write_authority":False,"entries":entries})
    result={"schema":"live-infinita-animal-approach-core-status/v1","world_id":world_id,"generated_at_unix":now(),"source":"memoria.ia-local-structural-api",
            "acked_this_poll":acked,"confirmed_total":state["confirmed"],"recovered_this_poll":fetched,"cached_recovered":len(entries),
            "eligible_in_source":len(eligible),"censored_in_source":sum(r["censored"] for r in scoped),"pending_intention":bool(snapshot["pending"]),
            "world_write_authority":False,"capture":False,"decision_use":False,"learned_hunting":False}
    if public is not None:write_checkpoint(public,result,mode=0o644)
    return result
if __name__=="__main__":
    try:print(json.dumps(sync_once(),sort_keys=True))
    except Exception as exc:
        print(json.dumps({"status":"failed","error_type":type(exc).__name__}))
        raise SystemExit(1)
