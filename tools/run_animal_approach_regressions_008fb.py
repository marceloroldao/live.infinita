#!/usr/bin/env python3
"""Run the exporter regression list with observed approach on and off."""
import argparse,json,os,pathlib,re,subprocess
ROOT=pathlib.Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
p.add_argument("--output-dir",type=pathlib.Path,required=True)
a=p.parse_args();a.output_dir.mkdir(parents=True,exist_ok=True)
names=(ROOT/"deploy/export-world-map-preview-web.sh").read_text().split("for extra_smoke in ",1)[1].split("; do",1)[0].split()
names.insert(0,"godot_world_map_traversal_smoke.gd")
engine="/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64"
all_rows=[]
for mode,flag in (("on","1"),("off","0")):
    env=dict(os.environ,LIVE_INFINITA_NAVIGATION_COST_SHIFT="1",LIVE_INFINITA_NAVIGATION_CONTACT_TURNS="1",
             LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION="1",LIVE_INFINITA_NAVIGATION_FAILURE_PREFERENCE="1",
             LIVE_INFINITA_ANIMAL_APPROACH_ENABLED=flag,LIVE_INFINITA_ANIMAL_CONTEXT_ENABLED=flag)
    rows=[];lines=[]
    for name in names:
        run=subprocess.run([engine,"--headless","--audio-driver","Dummy","--path",str(a.project),
            "--script",str(ROOT/"tests"/name),"--","--offline-tour"],env=env,capture_output=True,text=True,timeout=60)
        log=run.stdout+run.stderr
        ok=run.returncode==0 and not re.search(r"SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:",log,re.M)
        rows.append({"test":name,"passed":ok});lines.append(name+(" PASS" if ok else " FAIL"))
        if "animal" in name or not ok:(a.output_dir/(mode+"_"+name+".txt")).write_text(log)
        print(mode,lines[-1],flush=True)
    (a.output_dir/("regressions_"+mode+".json")).write_text(json.dumps(rows,indent=2)+"\n")
    (a.output_dir/("regressions_"+mode+".txt")).write_text("\n".join(lines)+"\n")
    all_rows.extend(rows)
assert len(all_rows)==2*len(names) and all(r["passed"] for r in all_rows)
print("008FB_"+str(len(all_rows))+"_REGRESSIONS_PASS",flush=True)
