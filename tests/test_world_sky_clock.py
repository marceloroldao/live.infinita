import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from world_sky_clock import sky_clock

class SkyClockTest(unittest.TestCase):
    def test_persistence_pause_and_invalid_inputs(self):
        with TemporaryDirectory() as d:
            p=Path(d)/"clock.json"
            self.assertIsNone(sky_clock(p,"world"))
            raw={"clock_schema":"simulation_clock_v1","tick":7200,"tick_duration_ms":500,"paused":False}
            p.write_text(json.dumps(raw))
            first=sky_clock(p,"world")
            self.assertEqual(first["logical_time_ms"],3600000)
            self.assertEqual(first,sky_clock(p,"world"))
            raw["paused"]=True
            p.write_text(json.dumps(raw))
            self.assertTrue(sky_clock(p,"world")["paused"])
            for field,bad in [("tick",True),("tick",-1),("tick",1.5),("tick",10**13),("tick_duration_ms",0),("paused",1)]:
                v={**raw,field:bad};p.write_text(json.dumps(v))
                self.assertIsNone(sky_clock(p,"world"))
            p.write_text("[]" )
            self.assertIsNone(sky_clock(p,"world"))
            p.write_text("x"*4097)
            self.assertIsNone(sky_clock(p,"world"))
            p.unlink();p.symlink_to(Path(d)/"missing")
            self.assertIsNone(sky_clock(p,"world"))
