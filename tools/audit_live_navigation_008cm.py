"""Audit completed live episodes without changing renderer, navigation or memory."""
from collections import Counter
from hashlib import sha256
import argparse
import json
import math
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"apps/world-runtime"))
from nov_navigation_episode_sync import read_source, SOURCE
from nov_spatial_memory_sync import _canonical

def distance(a,b):
    return math.hypot(a[0]-b[0],a[1]-b[1])

def changed(action,baseline):
    point=action.get("perception",{}).get(baseline)
    return isinstance(point,list) and len(point)==2 and distance(action["selected"],point)>0.05

def metrics(rows):
    completed=[a for a in rows if a["outcome"] in ("step_reached","goal_reached")]
    return {"actions":len(rows),"completed_steps":len(completed),
        "goals_reached":sum(a["outcome"]=="goal_reached" for a in rows),
        "collisions":sum(a["collisions"] for a in rows),
        "outcomes":dict(Counter(a["outcome"] for a in rows)),
        "interruption_reasons":dict(Counter(a["reason"] for a in rows if a["outcome"]=="interrupted")),
        "observed_distance_m":round(sum(distance(a["start"],a["end"]) for a in rows),4),
        "recorded_action_duration_seconds":round(sum(a["duration_ms"] for a in rows)/1000,4)}

def route_metrics(actions):
    # A retained window may start midway through a route; reaching its goal
    # does not establish coverage of the complete trip.
    groups={}
    missing=0
    for action in actions:
        route_id=action.get("route_goal_id","")
        if not route_id:
            missing+=1
            continue
        key=(action["context_start"]["world_id"],route_id)
        groups.setdefault(key,[]).append(action)
    result=[]
    for (world,route_id),rows in sorted(groups.items()):
        ordered=sorted(rows,key=lambda a:(a["started_at_unix"],a["decision_serial"]))
        goals={tuple(a["goal"]) for a in rows}
        consistent=all(distance(ordered[0]["goal"],goal)<=0.001 for goal in goals)
        result.append({"world_id":world,"route_goal_id":route_id,
            "goal_consistent":consistent,
            "goal":ordered[0]["goal"] if consistent else None,
            "first_observed_at_unix":ordered[0]["started_at_unix"],
            "last_observed_at_unix":max(a["ended_at_unix"] for a in rows),
            "last_remaining_goal_m":ordered[-1]["remaining_goal_m"],
            "goal_reached_observed":any(a["outcome"]=="goal_reached" for a in rows),
            "full_route_coverage_proven":False,
            "observed":metrics(rows),
            "causal_ram_actions":sum(a.get("working_memory_changed_choice") is True
                and changed(a,"without_working_memory") for a in rows),
            "causal_memoria_actions":sum(a["decision_source"]=="memoria.ia"
                and changed(a,"without_memoria") for a in rows)})
    return {"routes":result,"actions_without_route_identity":missing}

def audit(data):
    actions=[]
    identities={}
    duplicates=0
    for episode in data["episodes"]:
        for action in episode["actions"]:
            identity=episode["session_id"]+":"+str(action["decision_serial"])
            if identity in identities:
                if identities[identity]!=action:
                    raise ValueError("audit_action_identity_changed")
                duplicates+=1
                continue
            identities[identity]=action
            actions.append(action)
    ram=[a for a in actions if a.get("working_memory_changed_choice") is True and changed(a,"without_working_memory")]
    persistent=[a for a in actions if a["decision_source"]=="memoria.ia" and changed(a,"without_memoria")]
    claimed_ram=[a for a in actions if a.get("working_memory_changed_choice") is True]
    claimed_persistent=[a for a in actions if a["decision_source"]=="memoria.ia"]
    addresses=Counter(a.get("working_memory_key","") for a in ram)
    repeats=[{"address":k,"causal_actions":v} for k,v in addresses.most_common() if v>=2]
    examples=[]
    for a in (ram+persistent)[:5]:
        baseline="without_memoria" if a["decision_source"]=="memoria.ia" else "without_working_memory"
        examples.append({"source":a["decision_source"],"decision_serial":a["decision_serial"],
            "outcome":a["outcome"],"start":a["start"],"selected":a["selected"],
            "baseline":a["perception"][baseline],"observation_id":a["memory_observation_id"]})
    return {"schema":"live-infinita-live-navigation-audit/v1",
        "scope":"observed_live_native_episode_window",
        "generated_at_unix":time.time(),"source_snapshot_sha256":sha256(_canonical(data)).hexdigest(),
        "world_write_authority":False,"production_memory_written":False,
        "episode_ids":[e["episode_id"] for e in data["episodes"]],
        "source_retention_dropped":data["dropped_episodes"],"duplicate_actions_ignored":duplicates,
        "window_started_at_unix":min((a["started_at_unix"] for a in actions),default=None),
        "window_ended_at_unix":max((a["ended_at_unix"] for a in actions),default=None),
        "world_ids":sorted({a["context_start"]["world_id"] for a in actions}),
        "committed_routes":route_metrics(actions),
        "all":metrics(actions),"decision_sources":dict(Counter(a["decision_source"] for a in actions)),
        "verified_causal_ram":metrics(ram),"verified_causal_memoria":metrics(persistent),
        "causal_claims_without_distinct_baseline":{"ram":len(claimed_ram)-len(ram),"memoria":len(claimed_persistent)-len(persistent)},
        "repeated_ram_addresses":repeats,"examples":examples,
        "controlled_live_gain_measured":False,
        "limitations":["Retention window is incomplete; absence here does not prove absence in the entire run.",
            "Completed steps do not prove completed routes or shorter routes.",
            "Baseline records an alternative choice; its physical outcome was not executed.",
            "Distances and durations describe different observed situations and are not a controlled comparison.",
            "Repeated quantized addresses do not guarantee identical terrain, start, goal or conditions."]}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--source",type=Path,default=SOURCE)
    parser.add_argument("--report",type=Path)
    args=parser.parse_args()
    report=audit(read_source(args.source))
    output=json.dumps(report,indent=2)+"\n"
    if args.report:
        if args.report.resolve()==args.source.resolve():
            raise ValueError("Audit cannot overwrite native source")
        args.report.write_text(output)
    print(json.dumps({"all":report["all"],"ram":report["verified_causal_ram"],
        "memoria":report["verified_causal_memoria"],"committed_routes":report["committed_routes"],
        "repeated_addresses":len(report["repeated_ram_addresses"]),
        "controlled_live_gain_measured":False},indent=2))
if __name__=="__main__":main()
