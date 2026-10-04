import copy
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from nov_navigation_episode_sync import sync_once, validate_episode, payload, SCHEMA
from nov_spatial_memory_sync import _observation_id

def episode(seq=1):
    context = {"world_id":"fixture","world_sequence":10,"observer_entity_id":"nov",
               "runtime_position":{"x":350.0,"y":340.0},"region_id":"fixture"}
    action = {"decision_serial":1,"started_at_unix":100.0,"ended_at_unix":101.0,
        "started_at_ms":100,"duration_ms":1000,"start":[0.0,0.0],"end":[0.0,1.0],
        "goal":[5.0,0.0],"selected":[0.0,1.0],"remaining_goal_m":5.1,
        "goal_kind":"projected_runtime_observer_position","context_start":context,
        "context_end":copy.deepcopy(context),"outcome":"step_reached","physical_attempt":True,"collisions":0,"surface":"terrain","reason":"",
        "decision_source":"memoria.ia","memory_observation_id":"structural-event:"+"a"*40,
        "perception":{"lookahead_m":3.0,"without_memoria":[1.0,0.0],
            "candidates":[{"point":[0.0,1.0],"allowed":True,"clear_ahead":True,"reason":""}]}}
    return {"episode_id":"b"*32+":"+str(seq),"session_id":"b"*32,"sequence":seq,
        "actions":[action],"coordinate_space":"godot-renderer-xz-metres",
        "world_write_authority":False,"chronological_episode":True}

def receipt(value, stored=True):
    return {"observation_id":_observation_id(value["event"]),"stored":stored,"duplicate":not stored,
        "backend":"sqlite","semantic_projection":False,"association_sync_deferred":True}

class EpisodeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.source=self.root/"source.json"; self.checkpoint=self.root/"checkpoint.json"
        self.write([episode()])
    def tearDown(self): self.temp.cleanup()
    def write(self, rows):
        self.source.write_text(json.dumps({"schema":SCHEMA,"episodes":rows,"dropped_episodes":0}))
    def test_context_and_causal_evidence_preserved(self):
        row=validate_episode(episode()); value=payload(row)
        self.assertEqual(value["provenance"]["episode_archive"]["sha256"],sha256(__import__("nov_spatial_memory_sync")._canonical(row)).hexdigest())
        self.assertEqual(value["provenance"]["decision_sources"],{"memoria.ia":1})
        self.assertFalse(value["provenance"]["world_write_authority"])
        self.assertEqual(value["provenance"]["world_ids"],["fixture"])
    def test_idempotent_restart_and_partial_ack(self):
        self.write([episode(1),episode(2)])
        sends=[]
        def send(value): sends.append(value); return receipt(value)
        result=sync_once(self.source,self.checkpoint,send,limit=1)
        self.assertEqual(result["acked"],1)
        result=sync_once(self.source,self.checkpoint,send)
        self.assertEqual(result["acked"],1)
        self.assertEqual(len(sends),2)
        self.assertEqual(sync_once(self.source,self.checkpoint,send)["acked"],0)
    def test_failed_ack_does_not_advance(self):
        def send(value):
            ack=receipt(value); ack["observation_id"]="wrong"; return ack
        with self.assertRaises(RuntimeError): sync_once(self.source,self.checkpoint,send)
        self.assertFalse(self.checkpoint.exists())
    def test_retry_after_api_commit_and_lost_response_is_identical(self):
        attempts=[]
        def lost(value): attempts.append(value); raise OSError("lost response")
        with self.assertRaises(OSError): sync_once(self.source,self.checkpoint,lost)
        def duplicate(value): attempts.append(value); return receipt(value,False)
        self.assertEqual(sync_once(self.source,self.checkpoint,duplicate)["acked"],1)
        self.assertEqual(attempts[0],attempts[1])
    def test_identity_mutation_rejected(self):
        sync_once(self.source,self.checkpoint,receipt)
        row=episode(); row["actions"][0]["end"]=[0.0,2.0]; self.write([row])
        with self.assertRaisesRegex(ValueError,"identity_changed"):sync_once(self.source,self.checkpoint,receipt)
    def test_invalid_action_rejected(self):
        mutations=[
            lambda a:a.update(end=[float("nan"),0]),
            lambda a:a.update(memory_observation_id=""),
            lambda a:a["context_end"].update(world_id="other"),
            lambda a:a["context_end"].update(world_sequence=9),
            lambda a:a.update(outcome="invented"),
            lambda a:a.update(goal_kind="semantic-goal"),
            lambda a:a["perception"]["candidates"][0].update(allowed=1),
        ]
        for mutation in mutations:
            row=episode();mutation(row["actions"][0])
            with self.assertRaises(ValueError): validate_episode(row)
    def test_non_memory_outcome_cannot_claim_memory_id(self):
        row=episode();row["actions"][0]["decision_source"]="perception"
        with self.assertRaises(ValueError):validate_episode(row)
    def test_temporal_order_rejected(self):
        row=episode();second=copy.deepcopy(row["actions"][0]);second["started_at_ms"]=200
        row["actions"].append(second)
        with self.assertRaises(ValueError):validate_episode(row)
    def test_missing_native_file_is_waiting(self):
        self.source.unlink()
        self.assertEqual(sync_once(self.source,self.checkpoint,receipt)["status"],"awaiting_native_episode")
    def test_source_retention_disclosed_and_bounded(self):
        self.write([episode(n+1) for n in range(17)])
        with self.assertRaises(ValueError):sync_once(self.source,self.checkpoint,receipt)
    def test_full_episode_archived_before_post_and_reused(self):
        def send(value):
            p=self.root/value["provenance"]["episode_archive"]["relative_path"]
            self.assertEqual(json.loads(gzip.decompress(p.read_bytes())),episode())
            return receipt(value)
        sync_once(self.source,self.checkpoint,send)
        self.assertEqual(sync_once(self.source,self.checkpoint,send)["acked"],0)
    def test_compact_payload_does_not_repeat_full_perceptions(self):
        row=episode(); row["actions"]=[copy.deepcopy(row["actions"][0]) for _ in range(128)]
        value=payload(row)
        self.assertLess(len(json.dumps(value)),4000)
        self.assertNotIn("episode",value["provenance"])
    def test_incomplete_source_never_posts(self):
        self.source.write_text('{"schema":')
        with self.assertRaises(ValueError):sync_once(self.source,self.checkpoint,receipt)

if __name__=="__main__":unittest.main()
