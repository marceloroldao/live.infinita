"""Synthetic contract cases for the read-only observer; never enter live memory."""
from copy import deepcopy
import json
import unittest
from measure_live_pattern_outcomes_008el import measure

class OutcomeMeasurementTests(unittest.TestCase):
    def setUp(self):
        self.decision = {'contact_id': 'contact', 'world_id': 'w', 'context': 'signature',
            'side': -1, 'default_side': 1, 'changed_initial_side': True,
            'source': 'recovered-pattern-evidence', 'observation_ids': ['structural-event:'+'a'*40],
            'evaluation': {'reason': 'preferred_side', 'recommendation': {'side': -1,
                'source': 'recovered-pattern-evidence', 'observation_ids': ['structural-event:'+'a'*40]}}}
        self.outcome = {'attempt_id': 'contact', 'world_id': 'w', 'context': 'signature', 'side': -1,
            'physical_attempt': True, 'contains_prediction': False, 'distance_m': 4.0,
            'outcome': 'contour_completed', 'completion_basis': 'executed_exit', 'exit_progress_m': 1.0}
    def run_rows(self, outcome=True, excluded=None, extra=None):
        lines = ['NOV_PATTERN_DECISION '+json.dumps(self.decision)]
        if outcome:lines.append('NOV_PATTERN_OUTCOME '+json.dumps(self.outcome))
        if excluded:lines.append('NOV_PATTERN_EXCLUDED '+json.dumps(excluded))
        lines.extend(extra or [])
        return measure(lines)
    def test_changed_core_completed_is_observed_not_causal_gain(self):
        r=self.run_rows()
        self.assertEqual(r['counts'], {'core_changed_completed':1})
        self.assertFalse(r['performance_advantage_demonstrated'])
    def test_same_side_is_not_counted_as_changed(self):
        self.decision.update(default_side=-1,changed_initial_side=False)
        self.assertEqual(self.run_rows()['counts'], {'core_same_completed':1})
    def test_exploration_is_never_learned_preference(self):
        self.decision['source']='pattern-exploration'
        self.assertEqual(self.run_rows()['counts'], {'exploration_completed':1})
    def test_exclusion_is_not_success_or_failure(self):
        r=self.run_rows(outcome=False,excluded={'contact_id':'contact','world_id':'w','reason':'new_contact_before_executed_exit'})
        self.assertEqual(r['counts'], {'core_changed_excluded':1})
    def test_missing_result_is_unresolved_not_failure(self):
        self.assertEqual(self.run_rows(outcome=False)['counts'], {'core_changed_unresolved':1})
    def test_scope_prediction_and_progress_are_validated(self):
        for key,value in [('world_id','other'),('context','different'),('side',1),('contains_prediction',True),('exit_progress_m',0.4),('distance_m',float('nan'))]:
            with self.subTest(key=key):
                original=deepcopy(self.outcome);self.outcome[key]=value
                self.assertEqual(self.run_rows()['counts'], {'invalid_contact':1})
                self.outcome=original
    def test_duplicate_is_idempotent_but_changed_fact_is_invalid(self):
        line='NOV_PATTERN_OUTCOME '+json.dumps(self.outcome)
        self.assertEqual(self.run_rows(extra=[line])['counts'], {'core_changed_completed':1})
        changed=dict(self.outcome,distance_m=5)
        self.assertEqual(self.run_rows(extra=['NOV_PATTERN_OUTCOME '+json.dumps(changed)])['counts'], {'invalid_contact':1})
    def test_exclusion_and_completion_conflict_is_not_hidden(self):
        r=self.run_rows(excluded={'contact_id':'contact','world_id':'w','reason':'goal_changed'})
        self.assertEqual(r['counts'], {'invalid_contact':1})
    def test_bad_diagnostic_and_false_change_do_not_crash_or_credit(self):
        for evaluation in [None,[],{'recommendation':[]}]:
            self.decision['evaluation']=evaluation
            self.assertEqual(self.run_rows()['counts'], {'invalid_contact':1})
        self.setUp();self.decision['changed_initial_side']=False
        self.assertEqual(self.run_rows()['counts'], {'invalid_contact':1})
    def test_actual_failure_and_unapplied_preference_are_separate(self):
        self.outcome.update(outcome='stuck_recovery',completion_basis='stuck_recovery')
        self.assertEqual(self.run_rows()['counts'], {'core_changed_physical_failure':1})
        self.decision.update(side=1,default_side=1,changed_initial_side=False)
        self.outcome.update(side=1,outcome='contour_completed',completion_basis='executed_exit')
        self.assertEqual(self.run_rows()['counts'], {'core_not_applied_completed':1})

if __name__=='__main__':unittest.main()
