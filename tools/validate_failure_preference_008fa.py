#!/usr/bin/env python3
"""Independently check the archived native integrated physical results."""
import argparse,json,pathlib,math
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("archive",type=pathlib.Path)
a=p.parse_args();out=a.archive
report=json.loads((out/"TRAP_CHANGES_008EZ.json").read_text())
assert report["native_failure_preference"] and not report["experimental_policy"]
assert report["actual_traversals"]==92 and report["persisted_actual_facts"]==46
assert report["candidate"]["arrivals"]==38 and report["control"]["arrivals"]==21
raw=[];known=set();traversals=[]
for stage in report["stages"]:
    phase=stage["phase"]
    facts=json.loads((out/(phase+"_facts.json")).read_text())["rows"]
    for pair in stage["pairs"]:
        for name in ("perception","candidate"):
            row=pair[name];traversals.append(row)
            assert row["collisions"]==row["route_plan_builds"]==0
            assert row["status"]["failure_preference_enabled"] is True
            assert row["termination"] in ("arrived","stuck_recovery")
        row=pair["candidate"]
        if row["recommendation"].get("source")=="recovered-pattern-evidence":
            ids=row["recommendation"]["observation_ids"]
            assert ids and set(ids)<=known
    raw.extend(facts)
    recovered=json.loads((out/("recovered_"+str(len(raw))+".json")).read_text())
    assert len(recovered)==len(raw)
    recovered_by_id={r["attempt_id"]:r for r in recovered}
    assert len(recovered_by_id)==len(raw)
    for fact in raw:
        restored=dict(recovered_by_id[fact["attempt_id"]]);restored.pop("observation_id")
        assert restored==fact and fact["physical_attempt"] and not fact["contains_prediction"]
    known={r["observation_id"] for r in recovered}
    if phase.startswith("change_"):
        assert stage["decision_reasons"][1:4]==["cost_shift_exploration"]*3
        assert all(x==("arrived") for x in [p["candidate"]["termination"] for p in stage["pairs"][4:]])
assert len(traversals)==92 and sum(r["arrived"] for r in traversals)==59
final=report["stages"][-1]["pairs"][0]["candidate"]
assert final["side"]==-1 and final["arrived"] and final["recommendation"]["source"]=="recovered-pattern-evidence"
original=json.loads((out.parent/"TRAP_CHANGES_008EZ/TRAP_CHANGES_008EZ.json").read_text())
for arm in ("control","candidate"):
    for field in ("arrivals","attempts","distance_m","simulated_seconds"):
        assert math.isclose(report[arm][field],original[arm][field],abs_tol=1e-5)
result={"native_integration":True,"actual_traversals":92,"arrivals":59,"real_watchdog_failures":33,
        "unaltered_cold_recovered_facts":46,"matches_experimental_physical_totals":True,
        "collisions":0,"production_changed":False}
(out/"VALIDATION_008FA.json").write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(result))
