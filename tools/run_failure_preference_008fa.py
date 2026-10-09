#!/usr/bin/env python3
"""Exercise the native flag with real physics and strict cold SDK recovery."""
import argparse,pathlib
from run_trap_changes_008ez import run
p=argparse.ArgumentParser(description=__doc__)
p.add_argument("--project",type=pathlib.Path,default=pathlib.Path("/home/etbra/008bz-godot-test"))
p.add_argument("--output-dir",type=pathlib.Path,required=True)
a=p.parse_args()
run(a.project,a.output_dir,integrated=True)
