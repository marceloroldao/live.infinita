"""Experimental two-context cost refresh; no live caller or world-write authority."""
from nov_animal_approach_context import recommend as previous_recommend,key,fact
EPOCH_MS=300000
SAMPLES_PER_CONTEXT=2
MAX_CONTEXTS=2
def recommend(candidates,entries,world,now):
    # This validates sightings, clocks, all fact identities and duplicates first.
    previous=previous_recommend(candidates,entries,world,now)
    if not candidates or previous["source"]=="recovered-failure-reassessment":return previous
    ordered=sorted(candidates,key=lambda c:(c["distance_m"],c["entity_id"]))
    groups={}
    for c in ordered:groups.setdefault(key(c["distance_m"],c["context"]),{"candidate":c,"rows":[]})
    if len(groups)!=MAX_CONTEXTS:return previous
    for entry in entries:
        value=fact({k:v for k,v in entry.items() if k!="observation_id"});row=value["approach"]
        if row["world_id"]!=world or row["ended_ms"]>now:continue
        k=key(row["initial_observed_remaining_m"],value["context"])
        if k in groups:groups[k]["rows"].append((value,entry["observation_id"]))
    # Unknown contexts remain perception-owned; do not invent a training schedule.
    if any(len(g["rows"])<SAMPLES_PER_CONTEXT for g in groups.values()):return previous
    epoch_start=int(now)//EPOCH_MS*EPOCH_MS
    evaluated=[]
    for k,g in groups.items():
        g["rows"].sort(key=lambda pair:(pair[0]["approach"]["ended_ms"],pair[0]["approach"]["id"]))
        # An attempt that began before the epoch cannot fill the new sampling budget.
        fresh=[r for r in g["rows"] if r[0]["approach"]["started_ms"]>=epoch_start]
        evaluated.append((k,g,fresh))
    diagnostics={"epoch_start_ms":epoch_start,"epoch_ms":EPOCH_MS,"sample_limit_per_context":SAMPLES_PER_CONTEXT,
                 "max_contexts":MAX_CONTEXTS,"uses_ram_counter":False,
                 "counts":[{"context_key":list(k),"measured_in_epoch":len(fresh)} for k,_,fresh in sorted(evaluated,key=lambda v:v[0])]}
    under=[item for item in evaluated if len(item[2])<SAMPLES_PER_CONTEXT]
    if not under:return dict(previous,cost_revalidation=diagnostics)
    k,g,fresh=min(under,key=lambda item:(len(item[2]),item[1]["rows"][-1][0]["approach"]["ended_ms"],
                                       item[1]["candidate"]["distance_m"],item[1]["candidate"]["entity_id"]))
    return {"entity_id":g["candidate"]["entity_id"],"source":"recovered-cost-revalidation",
            "reason":"probe_context_with_fewer_current_epoch_outcomes",
            "observation_ids":[identity for _,identity in g["rows"][-SAMPLES_PER_CONTEXT:]],
            "cost_revalidation":diagnostics}
