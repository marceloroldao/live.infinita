#!/usr/bin/env python3
"""Read-only descriptive linkage of exploration and later applied learned choices."""
import argparse,json,math
from collections import Counter,defaultdict
from pathlib import Path
from statistics import mean
from measure_live_pattern_outcomes_008el import measure,MAX_EVENTS
APPLIED={"ram_same_completed","ram_changed_completed","core_same_completed","core_changed_completed"}
def analyze(report):
    if report.get("schema")!="live-infinita-pattern-outcome-measurement/v1":
        raise ValueError("Unknown measurement schema")
    if report.get("invalid_event_lines")!=0 or report.get("conflicting_contact_ids") or report.get("outcomes_without_decision")!=0:
        raise ValueError("Capture contains invalid/conflicting/unjoined events")
    contacts=report.get("contacts")
    if not isinstance(contacts,list) or len(contacts)>MAX_EVENTS:raise ValueError("Bounded contacts required")
    lines=[]
    for c in contacts:
        lines.append("NOV_PATTERN_DECISION "+json.dumps(c["decision"]))
        if c.get("outcome") is not None:lines.append("NOV_PATTERN_OUTCOME "+json.dumps(c["outcome"]))
        if c.get("exclusion") is not None:lines.append("NOV_PATTERN_EXCLUDED "+json.dumps(c["exclusion"]))
    if len(lines)>MAX_EVENTS:raise ValueError("Event bound exceeded")
    checked=measure(lines)
    if len(checked["contacts"])!=len(contacts):raise ValueError("Duplicate contact identity")
    if any(c["classification"]=="invalid_contact" for c in checked["contacts"]):raise ValueError("Invalid contact")
    declared={c["contact_id"]:c["classification"] for c in contacts}
    if any(declared.get(c["contact_id"])!=c["classification"] for c in checked["contacts"]):raise ValueError("Classification does not match evidence")
    groups=defaultdict(list)
    for c in checked["contacts"]:
        decision=c["decision"];shift=decision.get("evaluation",{}).get("cost_shift")
        if shift is None:continue
        if not isinstance(shift,dict) or shift.get("basis")!="measured_cost_increase" or not isinstance(shift.get("onset_attempt_id"),str) or not shift["onset_attempt_id"]:
            raise ValueError("Invalid cost-window identity")
        outcome=c.get("outcome")
        if outcome is not None:
            t=outcome.get("ended_at_unix")
            if type(t) not in (int,float) or not math.isfinite(t) or t<=0:raise ValueError("Physical time missing")
        groups[(decision["world_id"],decision["context"],shift["onset_attempt_id"])].append(c)
    windows=[]
    for (world,context,onset),rows in sorted(groups.items()):
        explorations=sorted((c for c in rows if c["classification"]=="exploration_completed"),key=lambda c:c["outcome"]["ended_at_unix"])
        later=sorted((c for c in rows if c["classification"] in APPLIED and explorations and c["outcome"]["ended_at_unix"]>explorations[0]["outcome"]["ended_at_unix"]),key=lambda c:c["outcome"]["ended_at_unix"])
        initial=[c for c in explorations if later and c["outcome"]["ended_at_unix"]<later[0]["outcome"]["ended_at_unix"]]
        item={"world_id":world,"context":context,"onset_attempt_id":onset,
            "counts":dict(Counter(c["classification"] for c in rows)),
            "exclusion_reasons":dict(Counter(c["exclusion"].get("reason") for c in rows if c.get("exclusion"))),
            "observed_exploration_to_applied_learning":bool(initial and later),
            "initial_completed_exploration_ids":[c["contact_id"] for c in initial],
            "later_applied_learned_ids":[c["contact_id"] for c in later],
            "later_changed_choices":sum("_changed_" in c["classification"] for c in later)}
        if initial and later:
            before=mean(c["outcome"]["distance_m"] for c in initial)
            after=mean(c["outcome"]["distance_m"] for c in later)
            item.update(initial_completed_exploration_mean_m=before,later_completed_learned_mean_m=after,
                descriptive_distance_delta_m=after-before,
                sides_before=[c["decision"]["side"] for c in initial],
                sides_after=[c["decision"]["side"] for c in later])
        windows.append(item)
    return {"schema":"live-infinita-adaptation-window-analysis/v1","scope":"read_only_observational",
        "counts":checked["counts"],
        "exploration_exclusion_reasons":dict(Counter(c["exclusion"].get("reason") for c in checked["contacts"] if c["classification"]=="exploration_excluded")),
        "windows":windows,"window_count":len(windows),
        "observed_conversion_windows":sum(w["observed_exploration_to_applied_learning"] for w in windows),
        "chronology_basis":"physical outcome ended_at_unix; capture array order is not assumed chronological",
        "performance_advantage_demonstrated":False,
        "limit":"Only completion timestamps are available; later completion does not establish a later decision start or causal use of the preceding exploration. Same sensor signature and onset do not identify the same obstacle geometry. Means include completed contacts only; failures and excluded contacts remain counted, with unknown censored costs. No causal advantage or acquisition-cost savings can be inferred.",
        "capture_since":report.get("since"),"capture_observed_at_utc":report.get("observed_at_utc")}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args()
    if a.input.stat().st_size>20_000_000:raise ValueError("Input too large")
    result=analyze(json.loads(a.input.read_text()))
    a.output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({"windows":result["window_count"],"observed_conversion_windows":result["observed_conversion_windows"],
        "counts":result["counts"],"performance_advantage_demonstrated":False}))
if __name__=="__main__":main()
