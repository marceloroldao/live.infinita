"""Experimental target selector; no live caller or world write authority."""
from nov_animal_approach_sync import validate,payload,number
from nov_spatial_memory_sync import _observation_id
def bucket(distance):
    return int(distance//6)
def recommend(candidates,entries,world,now_ms):
    # Inputs are fresh eye candidates supplied by the physical fixture, not a wildlife registry.
    if not isinstance(world,str) or not world or not number(now_ms,True) or not isinstance(candidates,list) or len(candidates)>16 or not isinstance(entries,list) or len(entries)>512:
        raise ValueError("invalid_candidate_scope")
    seen=set()
    for c in candidates:
        if not isinstance(c,dict) or set(c)!={"entity_id","distance_m"} or not isinstance(c["entity_id"],str) or not c["entity_id"].startswith(world+":rabbit:") or not number(c["distance_m"]) or not 6.5<c["distance_m"]<=24 or c["entity_id"] in seen:
            raise ValueError("invalid_visible_candidate")
        seen.add(c["entity_id"])
    ordered=sorted(candidates,key=lambda c:(c["distance_m"],c["entity_id"]))
    if not ordered:return {"source":"perception","entity_id":None,"reason":"no_visible_candidate"}
    baseline=ordered[0]
    result={"source":"perception","entity_id":baseline["entity_id"],"reason":"insufficient_comparable_evidence","observation_ids":[]}
    groups={};attempt_ids=set()
    for entry in entries:
        r=dict(entry);identity=r.pop("observation_id",None);r=validate(r)
        if identity!=_observation_id(payload(r)["event"]):raise ValueError("unverified_recovered_outcome")
        if r["id"] in attempt_ids:raise ValueError("duplicate_recovered_attempt")
        attempt_ids.add(r["id"])
        if r["world_id"]!=world or r["ended_ms"]>now_ms:continue
        groups.setdefault(bucket(r["initial_observed_remaining_m"]),[]).append((r,identity))
    evaluated=[]
    for candidate in ordered:
        rows=sorted(groups.get(bucket(candidate["distance_m"]),[]),key=lambda pair:(pair[0]["ended_ms"],pair[0]["id"]))[-2:]
        if len(rows)<2:return result
        score=sum(r["distance_m"]/3+20*(r["result"]!="approached") for r,_ in rows)/2
        evaluated.append((score,candidate,[identity for _,identity in rows]))
    best=min(evaluated,key=lambda item:(item[0],item[1]["distance_m"],item[1]["entity_id"]))
    initial=evaluated[0]
    result["reason"]="same_choice_as_perception" if best[1]["entity_id"]==baseline["entity_id"] else "improvement_below_margin"
    result["evaluations"]=[{"entity_id":c["entity_id"],"distance_bucket":bucket(c["distance_m"]),"score":score,"observation_ids":ids} for score,c,ids in evaluated]
    if best[1]["entity_id"]!=baseline["entity_id"] and best[0]<initial[0]*.8:
        result.update(source="recovered-approach-evidence",entity_id=best[1]["entity_id"],reason="lower_measured_cost_after_failures",
                      observation_ids=best[2]+initial[2])
    return result
