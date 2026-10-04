import copy
import gzip
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from nov_navigation_episode_sync import archive_once, archive_episode, read_source, validate_episode, integer, SCHEMA
from nov_navigation_promotion_sync import sync_once
from nov_spatial_memory_sync import _canonical
from test_nov_navigation_episode_sync import episode
from test_nov_navigation_promotion_sync import promotion, receipt, SCHEMA as PROMOTION_SCHEMA

def godot_reload(value):
    if type(value) is int:
        return float(value)
    if isinstance(value, dict):
        return {key:godot_reload(item) for key,item in value.items()}
    if isinstance(value, list):
        return [godot_reload(item) for item in value]
    return value

class NumericRestartTests(unittest.TestCase):
    def test_integral_numbers_only(self):
        self.assertEqual(integer(115.0),115)
        for value in (True,False,1.5,float("nan"),float("inf"),-1,10_000_000_001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                integer(value)

    def test_archive_restart_preserves_bytes_and_digest(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"source.json"
            row=episode()
            info=archive_episode(row,root)
            path=root/info["relative_path"]; before=path.read_bytes()
            source.write_text(json.dumps(godot_reload({"schema":SCHEMA,"episodes":[row],"dropped_episodes":0})))
            self.assertEqual(archive_once(source,root)["archived"],0)
            self.assertEqual(path.read_bytes(),before)
            loaded=read_source(source)["episodes"][0]
            self.assertEqual(archive_episode(loaded,root)["sha256"],sha256(gzip.decompress(before)).hexdigest())
            self.assertIs(type(loaded["sequence"]),int)
            self.assertIs(type(loaded["actions"][0]["decision_serial"]),int)

    def test_existing_numeric_variation_is_immutable_but_mutation_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); row=episode()
            info=archive_episode(row,root); path=root/info["relative_path"]
            historical=godot_reload(row)
            original=gzip.compress(_canonical(historical),mtime=0); path.write_bytes(original)
            self.assertEqual(archive_episode(validate_episode(row),root)["sha256"],sha256(_canonical(historical)).hexdigest())
            self.assertEqual(path.read_bytes(),original)
            row["actions"][0]["end"]=[0.0,2.0]
            with self.assertRaisesRegex(ValueError,"identity_changed"):
                archive_episode(row,root)

    def test_fractional_or_boolean_episode_counter_rejected(self):
        for value in (1.5,True):
            row=episode();row["sequence"]=value
            with self.assertRaises(ValueError):validate_episode(row)

    def test_promotion_restart_does_not_post_twice(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"source.json"; world=root/"world.json"; checkpoint=root/"checkpoint.json"
            world.write_text('{"world_id":"fixture"}')
            data={"schema":PROMOTION_SCHEMA,"world_id":"fixture","source":"native_renderer_working_memory",
                  "world_write_authority":False,"entries":[promotion()]}
            source.write_text(json.dumps(data))
            calls=[]
            def send(value):
                calls.append(copy.deepcopy(value));return receipt(value)
            self.assertEqual(sync_once(source,world,checkpoint,send)["acked"],1)
            source.write_text(json.dumps(godot_reload(data)))
            self.assertEqual(sync_once(source,world,checkpoint,send)["acked"],0)
            self.assertEqual(len(calls),1)

    def test_promotion_lost_ack_restart_has_identical_payload(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); source=root/"source.json"; world=root/"world.json"; checkpoint=root/"checkpoint.json"
            world.write_text('{"world_id":"fixture"}')
            data={"schema":PROMOTION_SCHEMA,"world_id":"fixture","source":"native_renderer_working_memory",
                  "world_write_authority":False,"entries":[promotion()]}
            calls=[]
            def lost(value):
                calls.append(copy.deepcopy(value));raise OSError("lost ack")
            source.write_text(json.dumps(data))
            with self.assertRaises(OSError):sync_once(source,world,checkpoint,lost)
            source.write_text(json.dumps(godot_reload(data)))
            def duplicate(value):
                calls.append(copy.deepcopy(value));ack=receipt(value);ack.update(stored=False,duplicate=True);return ack
            self.assertEqual(sync_once(source,world,checkpoint,duplicate)["acked"],1)
            self.assertEqual(calls[0],calls[1])
