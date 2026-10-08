#!/usr/bin/env python3
"""Isolated real capsule comparison; no production writes or core ingestion."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--engine',default='/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64')
    parser.add_argument('--comparison',choices=['contact-turns','exit-direction'],default='contact-turns')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parents[1]
    args.output_dir.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='008et-contact-turns-') as directory:
        work=Path(directory)
        shutil.copytree(repo/'apps/renderer-godot',work/'project',
            ignore=shutil.ignore_patterns('.godot','build'))
        environment={**os.environ,'XDG_DATA_HOME':str(work/'data'),
            'LIVE_INFINITA_NAVIGATION_COST_SHIFT':'1',
            'LIVE_INFINITA_NAVIGATION_CONTACT_TURNS':'1' if args.comparison=='exit-direction' else '0',
            'LIVE_INFINITA_NAVIGATION_EXIT_DIRECTION':'0',
            'LIVE_INFINITA_CONTACT_COMPARISON_MODE':args.comparison,
            'LIVE_INFINITA_CONTACT_TURN_OUTPUT':str(work/'physical.json')}
        completed=subprocess.run([args.engine,'--headless','--audio-driver','Dummy',
            '--path',str(work/'project'),'--script',str(repo/'tests/godot_contact_turns_008et.gd'),
            '--','--offline-tour'],env=environment,capture_output=True,text=True,timeout=180)
        log=completed.stdout+completed.stderr
        (args.output_dir/'physical.log').write_text(log)
        completed.check_returncode()
        if re.search(r'SCRIPT ERROR:|Parse Error:|Failed to load script|^ERROR:',log,re.M):
            raise RuntimeError('Godot error detected, comparison invalid')
        report=json.loads((work/'physical.json').read_text())
        if report['failures']!=0 or len(report['runs'])!=16:
            raise RuntimeError('Incomplete physical matrix')
        for row in report['runs']:
            if row['collisions']!=0 or row['route_plan_builds']!=0:
                raise RuntimeError('Physical collision or route-search contamination')
            if row['arm'].endswith('_continuity') and not row['arrived']:
                raise RuntimeError('Candidate failed to arrive')
        (args.output_dir/'physical.json.gz').write_bytes(
            gzip.compress((work/'physical.json').read_bytes(),mtime=0))
        summary={**report,'runs':[{k:v for k,v in row.items() if k!='actions'} for row in report['runs']]}
        summary['scope']='isolated real physics; policy property explicitly toggled per arm'
        summary['comparison']=args.comparison
        summary['memory_advantage_demonstrated']=False
        summary['limit']='Navigation/contact-lifecycle repair, not causal evidence of learned policy advantage. Failed baseline distances are bounded unfinished traversals.'
        (args.output_dir/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
        print(json.dumps({'runs':len(report['runs']),'continuous_arrivals':
            sum(row['arrived'] for row in report['runs'] if row['arm'].endswith('_continuity')),
            'baseline_arrivals':sum(row['arrived'] for row in report['runs'] if row['arm'].endswith('_baseline')),
            'failures':report['failures'],'output_dir':str(args.output_dir)}))
if __name__=='__main__':main()
