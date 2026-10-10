"""Synthetic execution-budget contracts; no learning-core writes."""
import json,tempfile,unittest,subprocess,os
from pathlib import Path
from hashlib import sha256
import test_cost_revalidation_008fj as fixtures
from nov_animal_exploration_guard import recommend_and_reserve,settle,search_budget,GuardError
ROOT=Path(__file__).resolve().parents[1]
ENGINE='/opt/live-infinita-godot/engine/Godot_v4.7.2-stable_linux.x86_64'
class SharedBudgetTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.journal=self.root/'search';self.guard=self.root/'guard'
        self.f=fixtures.CostRevalidationTests();self.f.setUp()
    def seal(self,count,pending=False):
        rows=[]
        for i in range(count):
            rows.append(dict(approach_id='w:animal-approach:search:'+str(i),entity_id='w:rabbit:1',world_id='w',started_ms=390000+i*1000,seed_observed_ms=389000,ended_ms=None,distance_m=None,reacquired_observed_ms=None,observed_position_m=None,result='renderer_restart',capture=False,absence_claim=False,approach_confirmed=False,learning_eligible=False,world_write_authority=False))
        p={}
        if pending:p=rows.pop();p['result']='reserved'
        value={'schema':'live-infinita-contact-search-journal/v1','records':rows,'pending':p,'clocks':{'w':400000}}
        raw=json.dumps(value);self.journal.write_text(json.dumps({'payload':raw,'sha256':sha256(raw.encode()).hexdigest()}))
    def choose(self,clock=400000):return recommend_and_reserve(self.guard,self.f.candidates(clock),self.f.entries(),'w',clock,contact_search_journal=self.journal)
    def test_pending_search_blocks_exploration(self):
        self.seal(1,True);self.assertEqual(self.choose()['reason'],'pending_reservation')
    def test_four_interrupted_searches_exhaust_shared_budget(self):
        self.seal(4);d=self.choose();self.assertEqual(d['reason'],'exploration_budget_exhausted');self.assertIsNone(d['reservation_token'])
    def test_three_searches_plus_one_exploration_use_all_slots(self):
        self.seal(3);d=self.choose();self.assertTrue(d['reservation_token']);self.assertEqual(d['exploration_budget']['used_attempts'],4)
    def test_corruption_and_rewind_fail_closed(self):
        self.seal(1)
        with self.assertRaises(GuardError):self.choose(399999)
        self.journal.write_text('{"payload":"{}","sha256":"wrong"}')
        with self.assertRaises(GuardError):self.choose()
    def test_unmeasured_interruption_cannot_claim_distance(self):
        self.seal(1);seal=json.loads(self.journal.read_text());value=json.loads(seal['payload']);value['records'][0]['distance_m']=1
        raw=json.dumps(value);self.journal.write_text(json.dumps({'payload':raw,'sha256':sha256(raw.encode()).hexdigest()}))
        with self.assertRaises(GuardError):self.choose()
    def test_godot_refuses_search_after_four_exploration_starts(self):
        for i in range(4):
            now=400000+i*2000;d=recommend_and_reserve(self.guard,self.f.candidates(now),self.f.entries(),'w',now)
            actual=self.f.fresh(80+i,False,True,now+1000)['approach'];actual['started_ms']=now;actual['ended_ms']=now+1000
            settle(self.guard,d['reservation_token'],actual)
        env=dict(os.environ,LIVE_INFINITA_TEST_SHARED_GUARD=str(self.guard),LIVE_INFINITA_TEST_SEARCH_JOURNAL=str(self.root/'native-search'))
        run=subprocess.run([ENGINE,'--headless','--audio-driver','Dummy','--path','/home/etbra/008bz-godot-test','--script',str(ROOT/'tests/godot_search_shared_guard_008fp.gd')],env=env,capture_output=True,text=True,timeout=30)
        self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertNotIn('ERROR:',run.stdout+run.stderr);self.assertIn('008FP_SHARED_GUARD_PASS',run.stdout)
if __name__=='__main__':unittest.main()
