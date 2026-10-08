"""Synthetic observer contracts; never ingested into live memory."""
from copy import deepcopy
import json
import unittest
from measure_live_pattern_outcomes_008el import measure
from analyze_adaptation_windows_008es import analyze

def contact(identity, time, source='pattern-exploration', onset='onset', side=-1):
    ids=['structural-event:'+'a'*40] if source=='recovered-pattern-evidence' else []
    recommendation={'side':-1,'source':source,'observation_ids':ids}
    d={'contact_id':identity,'world_id':'w','context':'signature','side':side,
       'default_side':1,'changed_initial_side':side!=1,'source':source,'observation_ids':ids,
       'evaluation':{'reason':'preferred_side','recommendation':recommendation,
           'cost_shift':{'basis':'measured_cost_increase','onset_attempt_id':onset}}}
    o={'attempt_id':identity,'world_id':'w','context':'signature','side':side,
       'physical_attempt':True,'contains_prediction':False,'distance_m':4.0,
       'outcome':'contour_completed','completion_basis':'executed_exit',
       'exit_progress_m':1.0,'ended_at_unix':time}
    return d,o
def capture(*pairs):
    lines=[]
    for d,o in pairs:
        lines.append('NOV_PATTERN_DECISION '+json.dumps(d))
        if o:lines.append('NOV_PATTERN_OUTCOME '+json.dumps(o))
    return measure(lines)
class AdaptationWindowTests(unittest.TestCase):
    def setUp(self):
        self.a=contact('exploration',10)
        self.b=contact('learned',20,'recovered-pattern-evidence')
    def test_physical_chronology_not_capture_order(self):
        report=capture(self.b,self.a)
        result=analyze(report)
        self.assertEqual(result['observed_conversion_windows'],1)
        report['contacts'].reverse()
        self.assertEqual(analyze(report),result)
        self.assertFalse(result['performance_advantage_demonstrated'])
    def test_ties_and_earlier_learning_do_not_convert(self):
        for time in [9,10]:
            self.b[1]['ended_at_unix']=time
            self.assertEqual(analyze(capture(self.a,self.b))['observed_conversion_windows'],0)
    def test_windows_are_isolated_by_onset(self):
        self.b[0]['evaluation']['cost_shift']['onset_attempt_id']='other'
        result=analyze(capture(self.a,self.b))
        self.assertEqual(result['window_count'],2)
        self.assertEqual(result['observed_conversion_windows'],0)
    def test_unapplied_recommendation_is_not_learning_transition(self):
        self.b=contact('learned',20,'recovered-pattern-evidence',side=1)
        result=analyze(capture(self.a,self.b))
        self.assertEqual(result['counts']['core_not_applied_completed'],1)
        self.assertEqual(result['observed_conversion_windows'],0)
    def test_same_side_preference_applied_is_separate_from_changed(self):
        self.b[0].update(default_side=-1,changed_initial_side=False)
        result=analyze(capture(self.a,self.b))
        self.assertEqual(result['counts']['core_same_completed'],1)
        self.assertEqual(result['windows'][0]['later_changed_choices'],0)
    def test_invalid_physical_times_rejected(self):
        for time in [True,0,-1,None,float('nan'),float('inf')]:
            with self.subTest(time=time):
                self.b[1]['ended_at_unix']=time
                with self.assertRaises(ValueError):analyze(capture(self.a,self.b))
    def test_classification_tampering_rejected(self):
        report=capture(self.a,self.b)
        report['contacts'][0]['classification']='core_changed_completed'
        with self.assertRaises(ValueError):analyze(report)
    def test_invalid_capture_rejected(self):
        for key,value in [('invalid_event_lines',1),('conflicting_contact_ids',['bad']),('outcomes_without_decision',1)]:
            report=capture(self.a,self.b);report[key]=value
            with self.assertRaises(ValueError):analyze(report)
    def test_censored_contacts_counted_without_cost_credit(self):
        d,_=contact('excluded',30)
        report=capture(self.a,self.b,(d,None))
        exclusion={'contact_id':'excluded','world_id':'w','reason':'goal_changed'}
        lines=[]
        for c in report['contacts']:
            lines.append('NOV_PATTERN_DECISION '+json.dumps(c['decision']))
            if c.get('outcome'):lines.append('NOV_PATTERN_OUTCOME '+json.dumps(c['outcome']))
        lines.append('NOV_PATTERN_EXCLUDED '+json.dumps(exclusion))
        result=analyze(measure(lines))
        self.assertEqual(result['counts']['exploration_excluded'],1)
        self.assertEqual(result['windows'][0]['later_completed_learned_mean_m'],4)
    def test_duplicate_identity_rejected(self):
        report=capture(self.a,self.b)
        report['contacts'].append(deepcopy(report['contacts'][0]))
        with self.assertRaises(ValueError):analyze(report)
if __name__=='__main__':unittest.main()
