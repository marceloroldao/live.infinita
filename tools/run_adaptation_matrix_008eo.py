#!/usr/bin/env python3
"""Measure adaptation costs across predeclared shifted openings; no production writes."""
import argparse,json,os,pathlib
import run_paired_adaptation_008en as paired
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008en-godot-test"))
    p.add_argument("--output-dir",type=pathlib.Path,required=True)
    p.add_argument("--resume",action="store_true",help="Reuse completed variant captures and run only missing ones")
    a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
    paired.native.SCRIPT=paired.native.ROOT/"tests/godot_adaptation_matrix_008eo.gd"
    summaries=[]
    for opening in (-20,0,10):
        os.environ["LIVE_INFINITA_CHANGED_OPENING"]=str(opening)
        target=a.output_dir/("opening_"+str(opening));target.mkdir(exist_ok=True)
        if a.resume and (target/"RESULT.json").exists():
            result=json.loads((target/"RESULT.json").read_text())
            assert result["changed_opening_z"]==opening
        else:
            result,*logs=paired.run(a.project)
            result["changed_opening_z"]=opening
            (target/"RESULT.json").write_text(json.dumps(result,indent=2)+"\n")
            for name,log in zip(("TRAINING","COMPARISON","REPAIRED"),logs):
                (target/(name+".txt")).write_text(log)
        baseline=result["changed_perception"];stale=result["changed_stale_core"]
        repaired=result["changed_repaired_core"];trials=result["adaptation_trials"]
        gain=stale["distance_m"]-repaired["distance_m"]
        extra=sum(r["distance_m"]-baseline["distance_m"] for r in trials)
        summary={"opening_z":opening,"baseline_distance_m":baseline["distance_m"],
            "stale_distance_m":stale["distance_m"],"repaired_distance_m":repaired["distance_m"],
            "baseline_seconds":baseline["simulated_seconds"],"stale_seconds":stale["simulated_seconds"],
            "repaired_seconds":repaired["simulated_seconds"],
            "repaired_source":repaired["recommendation"].get("source",""),
            "repaired_decision_reason":repaired["status"]["last_evaluation"].get("reason",""),
            "repaired_core_changed_initial_decisions":repaired["status"]["core_changed_initial_decisions"],
            "trial_sources":[r["recommendation"].get("source","") for r in trials],
            "first_learned_baseline_side_trial":next((i+1 for i,r in enumerate(trials) if r["side"]==1 and r["recommendation"].get("source","")=="ram-pattern-evidence"),None),
            "repaired_observation_ids":repaired["recommendation"].get("observation_ids",[]),
            "trial_sides":[r["side"] for r in trials],"adaptation_trials":len(trials),
            "first_baseline_side_trial":next((i+1 for i,r in enumerate(trials) if r["side"]==1),None),
            "excess_adaptation_distance_vs_perception_m":extra,
            "excess_adaptation_time_vs_perception_s":sum(r["simulated_seconds"]-baseline["simulated_seconds"] for r in trials),
            "future_saving_vs_stale_m":gain,"future_saving_vs_perception_m":baseline["distance_m"]-repaired["distance_m"],
            "stored_physical_outcomes":result["stored_physical_outcomes"],
            "acquisition_distance_m":result["acquisition_distance_m"],
            "collisions":sum(r["collisions"] for r in trials)+baseline["collisions"]+stale["collisions"]+repaired["collisions"],
            "rescues":sum(int(r["rescued"]) for r in trials)+int(baseline["rescued"])+int(stale["rescued"])+int(repaired["rescued"])}
        summaries.append(summary);print(json.dumps(summary),flush=True)
        (a.output_dir/"MATRIX_008EO.json").write_text(json.dumps({"schema":"live-infinita-adaptation-matrix/v1",
            "scope":"isolated_flat_wall_variants","planned_openings":[-20,0,10],"completed_variants":len(summaries),
            "variants":summaries,"production_improvement_demonstrated":False,
            "limit":"Related deterministic wall variants, not independent samples or generalization to terrain and live obstacles. Acquisition and excess adaptation costs are reported separately; no net gain over perception claimed."},indent=2)+"\n")
if __name__=="__main__":main()
