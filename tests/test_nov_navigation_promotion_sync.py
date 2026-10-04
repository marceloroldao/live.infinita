import copy
import json
from pathlib import Path
import tempfile
import unittest
from nov_navigation_promotion_sync import sync_once, read_source, payload, SCHEMA
from nov_spatial_memory_sync import _observation_id
from nov_navigation_episode_sync import archive_once
from test_nov_navigation_episode_sync import episode

def promotion():
    return {"summary":{"kind":"successful_route_step","key":"5,0|0,0",
        "from":[0.0,0.0],"to":[0.0,1.0],"goal":[5.0,0.0],"observed_count":1},
        "successful_causal_reuses":3,"decision_ids":["a"*32+":"+str(i) for i in (2,3,4)],
        "promoted_at_unix":100.0}

def receipt(value):
    return {"observation_id":_observation_id(value["event"]),"stored":True,"duplicate":False,
        "association_sync_deferred":True,"semantic_projection":False,"backend":"sqlite"}

class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/"source.json";self.world=self.root/"world.json";self.checkpoint=self.root/"checkpoint.json"
        self.world.write_text('{"world_id":"fixture"}')
        self.write([promotion()])
    def tearDown(self):self.temp.cleanup()
    def write(self,rows,world_id="fixture"):
        self.source.write_text(json.dumps({"schema":SCHEMA,"world_id":world_id,
            "source":"native_renderer_working_memory","world_write_authority":False,"entries":rows}))
    def test_empty_ram_does_not_write_to_memoria(self):
        self.write([])
        calls=[]
        result=sync_once(self.source,self.world,self.checkpoint,lambda value:calls.append(value))
        self.assertEqual(result["acked"],0);self.assertFalse(calls);self.assertFalse(self.checkpoint.exists())
    def test_promotion_confirmed_once_across_restart(self):
        calls=[]
        def send(value):calls.append(value);return receipt(value)
        self.assertEqual(sync_once(self.source,self.world,self.checkpoint,send)["acked"],1)
        self.assertEqual(sync_once(self.source,self.world,self.checkpoint,send)["acked"],0)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0]["provenance"]["promotion"]["successful_causal_reuses"],3)
    def test_failed_ack_does_not_mark_promoted(self):
        def send(value):
            result=receipt(value);result["observation_id"]="bad";return result
        with self.assertRaises(RuntimeError):sync_once(self.source,self.world,self.checkpoint,send)
        self.assertFalse(self.checkpoint.exists())
    def test_low_support_or_repeated_decision_rejected(self):
        row=promotion();row["successful_causal_reuses"]=2;self.write([row])
        with self.assertRaises(ValueError):read_source(self.source,"fixture")
        row=promotion();row["decision_ids"][2]=row["decision_ids"][0];self.write([row])
        with self.assertRaises(ValueError):read_source(self.source,"fixture")
    def test_other_world_is_not_ingested(self):
        self.write([promotion()],"different")
        calls=[]
        self.assertEqual(sync_once(self.source,self.world,self.checkpoint,lambda value:calls.append(value))["acked"],0)
        self.assertFalse(calls)
    def test_coordinate_key_mismatch_rejected(self):
        row=promotion();row["summary"]["from"]=[1.0,0.0];self.write([row])
        with self.assertRaises(ValueError):read_source(self.source,"fixture")
    def test_retry_identity_does_not_depend_on_other_candidates(self):
        first=payload(promotion(),"fixture")
        row=promotion();second=copy.deepcopy(row);second["summary"]["key"]="5,0|1,0";second["summary"]["from"]=[1.0,0.0]
        self.write([row,second])
        self.assertEqual(first,payload(read_source(self.source,"fixture")[0],"fixture"))
    def test_audit_archives_full_episode_without_memoria_posts(self):
        source=self.root/"episodes.json"
        source.write_text(json.dumps({"schema":"live-infinita-nov-navigation-episodes/v1","episodes":[episode()],"dropped_episodes":0}))
        result=archive_once(source,self.root)
        self.assertEqual(result["archived"],1);self.assertEqual(result["memoria_posts"],0)
        self.assertEqual(archive_once(source,self.root)["archived"],0)
        self.assertEqual(len(list((self.root/"navigation-episodes").glob("*.gz"))),1)
    def test_missing_promotion_file_waits(self):
        self.source.unlink()
        self.assertEqual(sync_once(self.source,self.world,self.checkpoint,receipt)["status"],"awaiting_ram_promotions")
if __name__=="__main__":unittest.main()
