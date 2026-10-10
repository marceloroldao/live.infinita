#!/usr/bin/env python3
"""Audit actual sensor transitions, not inferred animal absence."""
import argparse,json,pathlib

def transitions(movement):
    fact=movement['fact'];selected=fact['entity_id'];last=None;changes=[]
    trace=movement['visibility_trace']
    assert trace and trace[0]['ms']==fact['started_ms']
    for previous,current in zip(trace,trace[1:]):assert current['ms']-previous['ms']==300
    for row in trace:
        visible=any(x['entity_id']==selected for x in row['visible'])
        if visible!=last:
            changes.append({'relative_ms':row['ms']-fact['started_ms'],'visible':visible})
            last=visible
    assert changes[0]=={'relative_ms':0,'visible':True}
    assert not fact['absence_claim'] and not fact['capture'] and not fact['contains_prediction']
    assert not movement['future_position_given_to_controller'] and movement['animal_steps']>0
    return changes

def audit(report):
    assert report['actual_native_traversals']==24 and report['cold_recoveries']==16
    assert report['actual_facts_confirmed_and_recovered']==16 and not report['production_changed']
    cases={c['case']:c for c in report['cases']};results={}
    for name,case in cases.items():
        assert len(case['cold_recoveries'])==8
        assert case['perception_successes']==0
        results[name]=[]
        for pair in case['pairs']:
            assert not pair['control_outcome_ingested']
            a=pair['adaptive'];transitions(pair['perception_control']);changes=transitions(a)
            if name=='brief':
                assert a['fact']['result']=='approached' and a['fact']['revision']>=2
                assert changes==[{'relative_ms':0,'visible':True},{'relative_ms':3000,'visible':False},{'relative_ms':3600,'visible':True}]
                assert [x['direction'] for x in a['direction_changes']]==['x','z']
                assert a['animal_positions_final']['far'][0]>1
                fresh=[x['ms'] for x in a['visibility_trace'] if any(r['entity_id']==a['fact']['entity_id'] for r in x['visible'])]
                assert a['fact']['ended_ms']-max(fresh)<=300
                assert a['fact']['final_observed_remaining_m']<=6.5
            else:assert a['fact']['result']=='contact_lost'
            results[name].append({'entity_id':a['fact']['entity_id'],'result':a['fact']['result'],'transitions':changes,'decision_source':pair['decision']['source']})
    first=cases['prolonged']['pairs'][0]['adaptive'];changes=transitions(first)
    assert changes==[{'relative_ms':0,'visible':True},{'relative_ms':3000,'visible':False}]
    assert first['fact']['ended_ms']-first['fact']['started_ms']==4300
    assert cases['prolonged']['exploration_reservations']==3
    assert cases['brief']['exploration_reservations']==0
    return {'schema':'live-infinita-sensor-transition-audit/v1','cases':results,'brief_reacquisitions':4,'fresh_confirmed_approaches':4,'prolonged_first_stopped_before_screen_cleared':True,'production_changed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=pathlib.Path);p.add_argument('--output',type=pathlib.Path,required=True);args=p.parse_args()
    result=audit(json.loads(args.report.read_text()));args.output.write_text(json.dumps(result,indent=2)+'\n');print('008FN_SENSOR_AUDIT_PASS reacquisitions=4 fresh_successes=4')
