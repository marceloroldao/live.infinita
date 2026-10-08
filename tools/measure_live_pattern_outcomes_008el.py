#!/usr/bin/env python3
"""Read-only joins of executed native decisions and local physical outcomes."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import subprocess

PREFIXES = {'NOV_PATTERN_DECISION ': 'decision', 'NOV_PATTERN_OUTCOME ': 'outcome', 'NOV_PATTERN_EXCLUDED ': 'excluded'}
MAX_EVENTS = 5000

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def measure(lines):
    events = {name: {} for name in PREFIXES.values()}
    conflicts = set()
    invalid = 0
    for line in lines:
        for prefix, kind in PREFIXES.items():
            if not line.startswith(prefix):
                continue
            try:
                row = json.loads(line[len(prefix):])
                identity = row['attempt_id' if kind == 'outcome' else 'contact_id']
                if not isinstance(identity, str) or not identity:
                    raise ValueError('identity')
                previous = events[kind].get(identity)
                if previous is not None and previous != row:
                    conflicts.add(identity)
                events[kind][identity] = row
            except (ValueError, KeyError, TypeError):
                invalid += 1
            break
    counts = Counter()
    contacts = []
    for identity, decision in events['decision'].items():
        outcome = events['outcome'].get(identity)
        excluded = events['excluded'].get(identity)
        item = {'contact_id': identity, 'decision': decision, 'outcome': outcome, 'exclusion': excluded}
        valid = identity not in conflicts and not (outcome is not None and excluded is not None)
        side, default = decision.get('side'), decision.get('default_side')
        valid = valid and type(side) in (int, float) and side in (-1, 1) and type(default) in (int, float) and default in (-1, 1)
        valid = valid and isinstance(decision.get('world_id'), str) and bool(decision.get('world_id'))
        valid = valid and isinstance(decision.get('context'), str) and bool(decision.get('context'))
        valid = valid and type(decision.get('changed_initial_side')) is bool and decision['changed_initial_side'] == (side != default)
        source = decision.get('source')
        learned = source in ('ram-pattern-evidence', 'recovered-pattern-evidence')
        if learned:
            evaluation = decision.get('evaluation', {})
            if not isinstance(evaluation, dict):
                valid = False
                evaluation = {}
            recommendation = evaluation.get('recommendation', {})
            if not isinstance(recommendation, dict):
                valid = False
                recommendation = {}
            valid = valid and evaluation.get('reason') == 'preferred_side' and recommendation.get('source') == source
            proposed = recommendation.get('side')
            valid = valid and type(proposed) in (int, float) and proposed in (-1, 1)
            applied = proposed == side
            changed = applied and side != default and decision.get('changed_initial_side') is True
            if source == 'recovered-pattern-evidence':
                ids = decision.get('observation_ids', [])
                valid = valid and isinstance(ids, list) and bool(ids) and all(isinstance(v, str) and re.fullmatch(r'structural-event:[0-9a-f]{40}', v) for v in ids)
                valid = valid and ids == recommendation.get('observation_ids')
            arm = ('core' if source == 'recovered-pattern-evidence' else 'ram') + ('_changed' if changed else '_same' if applied else '_not_applied')
        else:
            arm = 'exploration' if source == 'pattern-exploration' else 'perception' if source == 'perception' else 'unknown'
            valid = valid and arm != 'unknown'
        if outcome is not None:
            valid = valid and all(outcome.get(k) == decision.get(k) for k in ('world_id', 'context', 'side'))
            valid = valid and outcome.get('physical_attempt') is True and outcome.get('contains_prediction') is False
            distance = outcome.get('distance_m')
            valid = valid and finite(distance) and distance >= 0
            result, basis = outcome.get('outcome'), outcome.get('completion_basis')
            if result == 'contour_completed':
                progress = outcome.get('exit_progress_m')
                valid = valid and (basis == 'goal_reached' or (basis == 'executed_exit' and finite(progress) and progress >= 0.75))
                terminal = 'completed'
            elif (result, basis) in (('blocked', 'physical_collision'), ('stuck_recovery', 'stuck_recovery')):
                terminal = 'physical_failure'
            else:
                valid = False
                terminal = 'invalid'
        elif excluded is not None:
            valid = valid and excluded.get('world_id') == decision.get('world_id') and isinstance(excluded.get('reason'), str)
            terminal = 'excluded'
        else:
            terminal = 'unresolved'  # Never infer pending/failure from missing logs.
        classification = arm + '_' + terminal if valid else 'invalid_contact'
        item['classification'] = classification
        counts[classification] += 1
        contacts.append(item)
    return {'schema': 'live-infinita-pattern-outcome-measurement/v1', 'counts': dict(counts),
            'contacts': contacts, 'invalid_event_lines': invalid, 'conflicting_contact_ids': sorted(conflicts),
            'outcomes_without_decision': len(set(events['outcome']) - set(events['decision'])),
            'scope': 'observational_read_only', 'performance_advantage_demonstrated': False,
            'comparison_limit': 'Different live geometry and equal baseline choices cannot establish causal improvement.'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--since', help='Journal timestamp; defaults to current renderer start.')
    parser.add_argument('--input-log', type=Path, help='Replay a previously captured journal instead of contacting systemd.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--capture-log', type=Path)
    args = parser.parse_args()
    since = args.since
    if args.input_log:
        if args.input_log.stat().st_size > 20_000_000:
            raise ValueError('Input exceeds bounded replay size')
        lines = args.input_log.read_text().splitlines()
    else:
        if not since:
            since = subprocess.check_output(['systemctl', 'show', 'live-infinita-renderer.service', '-p', 'ExecMainStartTimestamp', '--value'], text=True, timeout=10).strip()
            if not since:
                raise RuntimeError('Renderer start timestamp unavailable')
        log = subprocess.check_output(['journalctl', '-u', 'live-infinita-renderer.service', '--since', since,
                '--no-pager', '-o', 'cat', '--grep', 'NOV_PATTERN_(DECISION|OUTCOME|EXCLUDED)', '-n', str(MAX_EVENTS+1)], text=True, timeout=30)
        lines = log.splitlines()
    if len(lines) > MAX_EVENTS:
        raise ValueError('Event window too large; choose a narrower --since window')
    report = measure(lines)
    report['observed_at_utc'] = datetime.now(timezone.utc).isoformat()
    report['since'] = since
    report['input_event_lines'] = len(lines)
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + '\n'
    if args.output:
        args.output.write_text(encoded)
    if args.capture_log:
        args.capture_log.write_text('\n'.join(lines) + '\n')
    print(json.dumps({'counts': report['counts'], 'input_event_lines': len(lines),
                     'performance_advantage_demonstrated': False, 'output': str(args.output) if args.output else None}, ensure_ascii=False) if args.output else encoded)

if __name__ == '__main__':
    main()
