"""Exercise the exact root installer's read-only readiness block without root."""
import json,pathlib,subprocess,tempfile,time,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
SCRIPT=(ROOT/"deploy/apply-animal-approach-core-008fd-root.sh").read_text()
CODE=SCRIPT.split("<<'CHECK'\n",1)[1].split("\nCHECK",1)[0]
class RolloutTests(unittest.TestCase):
    def row(self):
        return {"schema":"live-infinita-animal-approach-core-status/v1","source":"memoria.ia-local-structural-api",
            "generated_at_unix":time.time(),"confirmed_total":5,"cached_recovered":5,"eligible_in_source":5,
            "world_write_authority":False,"capture":False,"decision_use":False,"learned_hunting":False}
    def probe(self,row):
        with tempfile.TemporaryDirectory() as folder:
            p=pathlib.Path(folder)/"public";p.write_text(json.dumps(row))
            code=CODE.replace("/var/www/live-infinita-godot/wildlife/approach-core.json",str(p)).replace("range(30)","range(3)").replace("time.sleep(1)","time.sleep(.01)")
            return subprocess.run(["python3","-c",code,str(time.time()-.1)],capture_output=True,text=True,timeout=3)
    def test_verified_recovery_ready(self):
        d=self.probe(self.row());self.assertEqual(d.returncode,0,d.stderr)
        self.assertIn("008FD_CORE_READY",d.stdout)
    def test_ack_without_recovery_rejected(self):
        r=self.row();r["cached_recovered"]=0
        self.assertNotEqual(self.probe(r).returncode,0)
    def test_stale_publication_rejected(self):
        r=self.row();r["generated_at_unix"]-=1
        self.assertNotEqual(self.probe(r).returncode,0)
    def test_learning_claim_rejected(self):
        r=self.row();r["learned_hunting"]=True
        self.assertNotEqual(self.probe(r).returncode,0)
    def test_empty_new_history_allowed(self):
        r=self.row();r.update(confirmed_total=0,cached_recovered=0,eligible_in_source=0)
        self.assertEqual(self.probe(r).returncode,0)
    def test_rollback_preserves_core_data(self):
        b=SCRIPT.split("rollback() {",1)[1].split("trap rollback ERR",1)[0]
        self.assertLess(b.index('systemctl stop "$SERVICE"'),b.index('for unit'))
        self.assertNotIn("rm -",b.split("Fatos confirmados",1)[1])
        self.assertNotIn("/var/lib/live-infinita/memoria-local",b)
if __name__=="__main__":unittest.main()
