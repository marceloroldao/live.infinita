"""Experimental physical context and failure-driven reassessment; no live caller."""
from hashlib import blake2b,sha256
from nov_animal_approach_sync import validate,number
from nov_spatial_memory_sync import _canonical,_observation_id
PROFILE="capsule044-height18-sweep4-v1"
KIND="native_contextual_approach_outcome"
def context(value):
    if not isinstance(value,dict) or set(value)!={"profile","sweep_m","blocked_ahead","sample_logical_ms"} or value["profile"]!=PROFILE or type(value["sweep_m"]) not in (int,float) or value["sweep_m"]!=4 or type(value["blocked_ahead"]) is not bool or not number(value["sample_logical_ms"],True):
        raise ValueError("invalid_physical_context")
    return dict(value,sweep_m=4.0,sample_logical_ms=int(value["sample_logical_ms"]))
def fact(value):
    if not isinstance(value,dict) or set(value)!={"approach","context","contacts"}:raise ValueError("invalid_contextual_fact")
    row=validate(value["approach"]);ctx=context(value["context"])
    if not row["learning_eligible"] or ctx["sample_logical_ms"]!=row["started_ms"] or type(value["contacts"]) is not int or not 0<=value["contacts"]<=10000:raise ValueError("unmeasured_contextual_fact")
    return {"approach":row,"context":ctx,"contacts":value["contacts"]}
def payload(value):
    value=fact(value);raw=_canonical(value);digest=sha256(raw).hexdigest();row=value["approach"]
    event={"version":1,"source_id":"live.infinita:contextual-approach-v1:"+digest,"sequence":1,"byte_offset":0,"byte_length":len(raw),
           "trail":[int.from_bytes(blake2b(str(k).encode(),digest_size=8).digest(),"big")&((1<<63)-1) for k in
                    (row["world_id"],value["context"]["profile"],value["context"]["blocked_ahead"],row["result"])],
           "relation_ids":[1],"signature":blake2b(raw,digest_size=8).hexdigest(),"resolution":1}
    return {"event":event,"provenance":{"hierarchy_id":"live:contextual-approaches:"+row["world_id"]+":nov","source_kind":KIND,
        "world_id":row["world_id"],"entity_id":"nov","world_write_authority":False,"contains_prediction":False,"outcome":value}}
def recover(response,world):
    if not isinstance(response,dict) or response.get("semantic_projection") is not False or not isinstance(response.get("items"),list) or len(response["items"])>100:raise ValueError("invalid_recovery")
    entries=[];seen=set()
    for envelope in response["items"]:
        if not isinstance(envelope,dict) or not isinstance(envelope.get("provenance"),dict):raise ValueError("invalid_envelope")
        p=envelope["provenance"]
        if p.get("source_kind")!=KIND or p.get("world_id")!=world:continue
        value=fact(p.get("outcome"));request=payload(value);identity=_observation_id(request["event"])
        if envelope.get("observation_id")!=identity or _canonical(envelope.get("event"))!=_canonical(request["event"]) or _canonical(p)!=_canonical(request["provenance"]):raise ValueError("recovered_context_mismatch")
        attempt=value["approach"]["id"]
        if attempt in seen:raise ValueError("duplicate_contextual_attempt")
        seen.add(attempt);entries.append(dict(value,observation_id=identity))
    return entries
def key(distance,ctx):
    return (int(distance//6),ctx["profile"],ctx["blocked_ahead"])
def recommend(candidates,entries,world,now):
    if not isinstance(candidates,list) or len(candidates)>16 or not isinstance(entries,list) or len(entries)>512 or not number(now,True) or not isinstance(world,str) or not world:raise ValueError("invalid_scope")
    ordered=[];seen=set()
    for c in candidates:
        if not isinstance(c,dict) or set(c)!={"entity_id","distance_m","context"} or not isinstance(c["entity_id"],str) or not c["entity_id"].startswith(world+":rabbit:") or not number(c["distance_m"]) or not 6.5<c["distance_m"]<=24 or c["entity_id"] in seen:raise ValueError("invalid_eye_candidate")
        ctx=context(c["context"])
        if ctx["sample_logical_ms"]>now or now-ctx["sample_logical_ms"]>300:raise ValueError("stale_candidate_context")
        seen.add(c["entity_id"]);ordered.append(dict(c,context=ctx))
    ordered.sort(key=lambda c:(c["distance_m"],c["entity_id"]))
    if not ordered:return {"entity_id":None,"source":"perception","reason":"no_visible_candidate","observation_ids":[]}
    groups={};attempts=set()
    for entry in entries:
        raw=dict(entry);identity=raw.pop("observation_id",None);value=fact(raw);row=value["approach"]
        if identity!=_observation_id(payload(value)["event"]):raise ValueError("unverified_contextual_evidence")
        if row["id"] in attempts:raise ValueError("duplicate_contextual_attempt")
        attempts.add(row["id"])
        if row["world_id"]!=world or row["ended_ms"]>now:continue
        groups.setdefault(key(row["initial_observed_remaining_m"],value["context"]),[]).append((value,identity))
    usable={key(c["distance_m"],c["context"]) for c in ordered}
    shocks=[]
    for k in usable:
        rows=sorted(groups.get(k,[]),key=lambda pair:(pair[0]["approach"]["ended_ms"],pair[0]["approach"]["id"]))
        for previous,current in zip(rows,rows[1:]):
            if previous[0]["approach"]["result"]=="approached" and current[0]["approach"]["result"]!="approached":
                shocks.append((current[0]["approach"]["ended_ms"],current[1]))
    shock=max(shocks,default=None)
    result={"entity_id":ordered[0]["entity_id"],"source":"perception","reason":"unseen_physical_context","observation_ids":[]}
    evaluated=[]
    for c in ordered:
        rows=sorted(groups.get(key(c["distance_m"],c["context"]),[]),key=lambda pair:(pair[0]["approach"]["ended_ms"],pair[0]["approach"]["id"]))
        if shock:rows=[r for r in rows if r[0]["approach"]["ended_ms"]>=shock[0]]
        evaluated.append((c,rows))
    if shock and any(len(rows)<2 for _,rows in evaluated):
        # Least sampled alternative first; no animal identity or obstacle position is privileged.
        c,rows=min(evaluated,key=lambda item:(len(item[1]),max((r[0]["approach"]["ended_ms"] for r in item[1]),default=-1),item[0]["distance_m"]))
        result.update(entity_id=c["entity_id"],source="recovered-failure-reassessment",reason="probe_under_sampled_context_after_failure",
                      observation_ids=[shock[1]],reassessment_since_ms=shock[0])
        return result
    if any(len(rows)<2 for _,rows in evaluated):return result
    scores=[]
    for c,rows in evaluated:
        latest=rows[-2:]
        score=sum(v["approach"]["distance_m"]/3+20*(v["approach"]["result"]!="approached") for v,_ in latest)/2
        scores.append((score,c,[identity for _,identity in latest]))
    best=min(scores,key=lambda item:(item[0],item[1]["distance_m"],item[1]["entity_id"]))
    result["reason"]="same_choice_as_perception"
    result["evaluations"]=[{"entity_id":c["entity_id"],"score":score,"context_key":list(key(c["distance_m"],c["context"])),"observation_ids":ids} for score,c,ids in scores]
    if best[1]["entity_id"]!=ordered[0]["entity_id"] and best[0]<scores[0][0]*.8:
        result.update(entity_id=best[1]["entity_id"],source="recovered-contextual-evidence",reason="lower_contextual_failure_cost",observation_ids=best[2]+scores[0][2])
    return result
