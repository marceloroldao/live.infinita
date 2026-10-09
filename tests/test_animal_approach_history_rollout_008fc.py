"""Test the exact installer readiness block without root or production changes."""
import json,pathlib,subprocess,tempfile,threading,time,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/'deploy/apply-animal-approach-history-008fc-root.sh').read_text()
CODE=SCRIPT.split("<<'CHECK'\n",1)[1].split('\nCHECK',1)[0]
class ReadinessTests(unittest.TestCase):
    def probe(self,row,replacement=None):
        with tempfile.TemporaryDirectory(prefix='008fc-readiness-') as folder:
            path=pathlib.Path(folder)/'status.json';path.write_text(json.dumps(row))
            code=CODE.replace('/var/www/live-infinita-godot/wildlife/search-intent.json',str(path)).replace('range(60)','range(25)').replace('time.sleep(1)','time.sleep(0.01)')
            started=time.time()-0.1
            if replacement:
                def publish():
                    time.sleep(.06)
                    replacement['generated_at_unix']=time.time()
                    tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(replacement));tmp.replace(path)
                thread=threading.Thread(target=publish);thread.start()
            result=subprocess.run(['python3','-c',code,str(started)],capture_output=True,text=True,timeout=3)
            if replacement:thread.join()
            return result
    def current(self):
        return {'generated_at_unix':time.time(),'source':'native_bounded_animal_search','world_write_authority':False,'last_error':None,'approach':{'enabled':True,'history':{'storage_ready':True,'persistent':True}},'counts':{}}
    def test_old_schema_waits_then_accepts_new_publication(self):
        old=self.current();old.pop('approach')
        result=self.probe(old,self.current())
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('008FC_NATIVE_OK',result.stdout)
    def test_old_schema_exhausts_budget_without_assertion(self):
        old=self.current();old.pop('approach')
        result=self.probe(old)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('RuntimeError',result.stderr)
        self.assertNotIn('AssertionError',result.stderr)
    def test_older_publication_is_rejected_even_with_new_flag(self):
        row=self.current();row['generated_at_unix']=time.time()-0.5
        result=self.probe(row)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('008FC_NATIVE_OK',result.stdout)
    def test_unready_history_cannot_pass(self):
        row=self.current();row['approach']['history']['storage_ready']=False
        self.assertNotEqual(self.probe(row).returncode,0)
    def test_ephemeral_history_cannot_pass(self):
        row=self.current();row['approach']['history']['persistent']=False
        self.assertNotEqual(self.probe(row).returncode,0)
    def test_rollback_stops_renderer_before_restoring_code(self):
        block=SCRIPT.split('rollback() {',1)[1].split('trap rollback ERR',1)[0]
        self.assertLess(block.index('systemctl stop live-infinita-renderer.service'),block.index('for f in'))
if __name__=='__main__':unittest.main()
